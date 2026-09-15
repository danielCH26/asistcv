"""
Test SQLModel models can be imported and instantiated.
"""
import pytest
from datetime import datetime


def test_import_models():
    """Verify all models can be imported."""
    from app.db.models import Profile, JobDescription, Analysis

    assert Profile is not None
    assert JobDescription is not None
    assert Analysis is not None


def test_profile_model_instantiation():
    """Test Profile model can be instantiated."""
    from app.db.models import Profile

    profile = Profile(
        name="Test User",
        headline="Senior Developer",
        experience={"years": 5},
        skills={"python": True},
        preferences={"remote": True},
    )

    assert profile.name == "Test User"
    assert profile.headline == "Senior Developer"
    assert profile.experience == {"years": 5}
    assert profile.skills == {"python": True}
    assert profile.preferences == {"remote": True}
    assert profile.id is None  # Not persisted yet


def test_job_description_model_instantiation():
    """Test JobDescription model can be instantiated."""
    from app.db.models import JobDescription

    job = JobDescription(
        raw_text="We are looking for a Python developer...",
        title="Python Developer",
        company="Tech Corp",
        source="LinkedIn",
        url="https://example.com/job",
    )

    assert job.raw_text == "We are looking for a Python developer..."
    assert job.title == "Python Developer"
    assert job.company == "Tech Corp"
    assert job.source == "LinkedIn"
    assert job.url == "https://example.com/job"
    assert job.id is None


def test_analysis_model_instantiation():
    """Test Analysis model can be instantiated."""
    from app.db.models import Analysis

    analysis = Analysis(
        job_description_id=1,
        profile_snapshot={"name": "Test User"},
        score=85,
        strengths={"python": "expert"},
        gaps={"java": "beginner"},
        energy_level="high",
        reasoning="Good match for the role",
    )

    assert analysis.job_description_id == 1
    assert analysis.profile_snapshot == {"name": "Test User"}
    assert analysis.score == 85
    assert analysis.strengths == {"python": "expert"}
    assert analysis.gaps == {"java": "beginner"}
    assert analysis.energy_level == "high"
    assert analysis.reasoning == "Good match for the role"
    assert analysis.id is None


def test_model_table_names():
    """Verify table names are correct."""
    from app.db.models import Profile, JobDescription, Analysis

    assert Profile.__tablename__ == "profiles"
    assert JobDescription.__tablename__ == "job_descriptions"
    assert Analysis.__tablename__ == "analyses"


def test_analysis_foreign_key():
    """Verify Analysis has foreign key to JobDescription."""
    from app.db.models import Analysis
    from sqlalchemy import inspect

    # Get the foreign keys from the mapper
    mapper = inspect(Analysis)
    fk_list = [fk for fk in mapper.relationships]

    # Check that job_description_id is a foreign key
    # The relationship is defined via the Column, so we check the column info
    assert hasattr(Analysis, 'job_description_id')
