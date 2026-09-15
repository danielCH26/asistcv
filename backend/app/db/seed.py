"""
Seed initial data for AsistCV database.

This creates a test profile to verify the database is working.
"""
from datetime import datetime


async def seed_initial_data():
    """
    Seed the database with initial test data.

    Creates a single test profile for development/testing purposes.
    """
    from app.db.session import get_session_context
    from app.db.models import Profile

    seed_data = {
        "name": "Test User",
        "headline": "Senior Python Developer",
        "experience": {
            "years": 5,
            "roles": ["Software Engineer", "Senior Developer"],
            "industries": ["Tech", "Finance"],
        },
        "skills": {
            "programming": ["Python", "JavaScript", "TypeScript"],
            "frameworks": ["FastAPI", "React", "Svelte"],
            "databases": ["PostgreSQL", "Redis"],
            "tools": ["Docker", "Git", "AWS"],
        },
        "preferences": {
            "locations": ["Remote", "New York"],
            "work_types": ["Full-time", "Contract"],
            "salary_range": {"min": 120000, "max": 180000},
        },
    }

    async with get_session_context() as session:
        # Check if profile already exists
        from sqlalchemy import select
        result = await session.execute(
            select(Profile).where(Profile.name == "Test User")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print("Seed data already exists, skipping...")
            return

        # Create the test profile
        profile = Profile(
            name=seed_data["name"],
            headline=seed_data["headline"],
            experience=seed_data["experience"],
            skills=seed_data["skills"],
            preferences=seed_data["preferences"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        session.add(profile)
        await session.commit()
        print(f"Created test profile: {profile.name} (ID: {profile.id})")


if __name__ == "__main__":
    import asyncio
    asyncio.run(seed_initial_data())
