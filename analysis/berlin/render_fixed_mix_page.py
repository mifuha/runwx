"""Extend the original checked Berlin page with the participant-mix follow-up."""
from pathlib import Path
import render_page
from fixed_mix_page import build_section


def build():
    original=render_page.build()
    marker='<section aria-labelledby="checked">'
    if original.count(marker)!=1:
        raise ValueError('original study insertion point differs')
    page=original.replace(marker,build_section()+'\n'+marker)
    return page.replace('No age/year adjustment, p-values or causal claims.',
        'The original recorded-group analysis does not adjust for age or calendar year. '
        'The participant-mix follow-up above adds those specific checks; neither study '
        'makes causal claims or reports p-values.')


if __name__=='__main__':
    output=Path(__file__).resolve().parents[2]/'src/runwx/api/static/berlin-case-study.html'
    output.write_bytes(build().replace('\r\n','\n').encode('utf-8'))
    print('Generated the page from the original study and checked participant-mix aggregates.')
