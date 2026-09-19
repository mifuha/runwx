"""FastAPI application for the read-only runwx MVP."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from google.cloud import bigquery
from starlette.concurrency import run_in_threadpool

from runwx.api.models import CourseComparison
from runwx.api.repository import (
    BigQueryComparisonRepository,
    ComparisonUnavailableError,
    UnknownCourseError,
)


class ComparisonService:
    """Keep the synchronous BigQuery client off the ASGI event loop."""

    def __init__(self, repository: BigQueryComparisonRepository):
        self._repository = repository

    async def get_course_comparison(self, course_slug: str) -> CourseComparison:
        return await run_in_threadpool(
            self._repository.get_course_comparison, course_slug
        )


@lru_cache
def get_repository() -> ComparisonService:
    return ComparisonService(
        BigQueryComparisonRepository(
            bigquery.Client(project="runwx-learning-mifuha", location="europe-west1")
        )
    )


app = FastAPI(
    title="runwx historical comparison API",
    version="0.1.0",
)


@app.get(
    "/api/courses/{course_slug}/comparison",
    response_model=CourseComparison,
    response_model_exclude_none=False,
)
async def get_course_comparison(
    course_slug: str,
    repository: Annotated[ComparisonService, Depends(get_repository)],
) -> CourseComparison:
    try:
        return await repository.get_course_comparison(course_slug)
    except UnknownCourseError as error:
        raise HTTPException(status_code=404, detail="course not found") from error
    except ComparisonUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail="comparison data is temporarily unavailable",
        ) from error
