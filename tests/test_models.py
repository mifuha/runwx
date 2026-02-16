import pytest
from datetime import datetime, timezone
from runwx.models import Run, WeatherObs


class TestRun:
    """Tests for the Run dataclass."""

    def test_valid_run(self):
        """Test creating a valid Run instance."""
        started_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        run = Run(
            started_at=started_at,
            duration_s=3600,
            distance_m=10000
        )
        assert run.started_at == started_at
        assert run.duration_s == 3600
        assert run.distance_m == 10000

    def test_run_timezone_aware_required(self):
        """Test that Run requires timezone-aware datetime."""
        started_at = datetime(2024, 1, 15, 10, 30, 0)  # timezone-naive
        with pytest.raises(ValueError, match="started_at must be timezone-aware"):
            Run(
                started_at=started_at,
                duration_s=3600,
                distance_m=10000
            )

    def test_run_duration_must_be_positive(self):
        """Test that duration_s must be positive."""
        started_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        
        with pytest.raises(ValueError, match="duration_s must be positive"):
            Run(
                started_at=started_at,
                duration_s=0,
                distance_m=10000
            )
        
        with pytest.raises(ValueError, match="duration_s must be positive"):
            Run(
                started_at=started_at,
                duration_s=-100,
                distance_m=10000
            )

    def test_run_distance_must_be_positive(self):
        """Test that distance_m must be positive."""
        started_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        
        with pytest.raises(ValueError, match="distance_m must be positive"):
            Run(
                started_at=started_at,
                duration_s=3600,
                distance_m=0
            )
        
        with pytest.raises(ValueError, match="distance_m must be positive"):
            Run(
                started_at=started_at,
                duration_s=3600,
                distance_m=-5000
            )

    def test_run_is_frozen(self):
        """Test that Run is a frozen dataclass (immutable)."""
        started_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        run = Run(
            started_at=started_at,
            duration_s=3600,
            distance_m=10000
        )
        
        with pytest.raises(Exception):  # FrozenInstanceError
            run.duration_s = 7200


class TestWeatherObs:
    """Tests for the WeatherObs dataclass."""

    def test_valid_weather_obs(self):
        """Test creating a valid WeatherObs instance."""
        observed_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        weather = WeatherObs(
            observed_at=observed_at,
            temp_c=15.5,
            wind_mps=5.2,
            precipitation_mm=0.0
        )
        assert weather.observed_at == observed_at
        assert weather.temp_c == 15.5
        assert weather.wind_mps == 5.2
        assert weather.precipitation_mm == 0.0

    def test_weather_obs_timezone_aware_required(self):
        """Test that WeatherObs requires timezone-aware datetime."""
        observed_at = datetime(2024, 1, 15, 12, 0, 0)  # timezone-naive
        with pytest.raises(ValueError, match="observed_at must be timezone-aware"):
            WeatherObs(
                observed_at=observed_at,
                temp_c=15.5,
                wind_mps=5.2,
                precipitation_mm=0.0
            )

    def test_weather_obs_negative_values_allowed(self):
        """Test that negative temperature, wind, and precipitation are allowed."""
        observed_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # Negative temperature (cold weather)
        weather1 = WeatherObs(
            observed_at=observed_at,
            temp_c=-10.0,
            wind_mps=0.0,
            precipitation_mm=0.0
        )
        assert weather1.temp_c == -10.0
        
        # Negative wind doesn't make physical sense, but no validation prevents it
        weather2 = WeatherObs(
            observed_at=observed_at,
            temp_c=20.0,
            wind_mps=-1.0,
            precipitation_mm=0.0
        )
        assert weather2.wind_mps == -1.0
        
        # Negative precipitation doesn't make physical sense, but no validation prevents it
        weather3 = WeatherObs(
            observed_at=observed_at,
            temp_c=20.0,
            wind_mps=0.0,
            precipitation_mm=-0.5
        )
        assert weather3.precipitation_mm == -0.5

    def test_weather_obs_is_frozen(self):
        """Test that WeatherObs is a frozen dataclass (immutable)."""
        observed_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        weather = WeatherObs(
            observed_at=observed_at,
            temp_c=15.5,
            wind_mps=5.2,
            precipitation_mm=0.0
        )
        
        with pytest.raises(Exception):  # FrozenInstanceError
            weather.temp_c = 20.0
