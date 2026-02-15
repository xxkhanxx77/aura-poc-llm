"""Seed script: inserts sample tenant, job, and resumes for testing.

Run via: docker compose exec -T app python scripts/seed_data.py
"""

import asyncio
import uuid

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.orm import Job, Resume, Tenant

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
RESUME_IDS = [
    uuid.UUID("33333333-3333-3333-3333-333333333301"),
    uuid.UUID("33333333-3333-3333-3333-333333333302"),
    uuid.UUID("33333333-3333-3333-3333-333333333303"),
]

JOB_DESCRIPTION = """Senior Backend Engineer

We are looking for a Senior Backend Engineer to join our platform team.

Requirements:
- 5+ years of backend development experience
- Strong Python skills (FastAPI, Django, or Flask)
- Experience with PostgreSQL and Redis
- Familiarity with Docker and Kubernetes
- Experience building RESTful APIs at scale
- Good communication skills and ability to mentor junior developers

Nice to have:
- Experience with event-driven architectures (Kafka, RabbitMQ)
- Machine learning / AI integration experience
- Contributions to open source projects"""

RESUMES = [
    {
        "id": RESUME_IDS[0],
        "name": "Alice Chen",
        "email": "alice.chen@example.com",
        "text": """Alice Chen
Senior Software Engineer | alice.chen@example.com

EXPERIENCE

Senior Backend Engineer — Stripe (2020-2024)
- Built and maintained payment processing microservices in Python (FastAPI)
- Designed PostgreSQL schemas handling 10M+ transactions/day
- Led team of 6 engineers on payment gateway rewrite
- Implemented Redis-based caching layer reducing API latency by 40%
- Deployed services to Kubernetes clusters across 3 regions

Backend Engineer — Dropbox (2017-2020)
- Developed file sync APIs serving 500M users
- Built event-driven pipelines with Kafka for real-time notifications
- Mentored 3 junior engineers through onboarding

EDUCATION
BS Computer Science, Stanford University (2017)

SKILLS
Python, FastAPI, Django, PostgreSQL, Redis, Kubernetes, Docker, Kafka, gRPC""",
    },
    {
        "id": RESUME_IDS[1],
        "name": "Bob Martinez",
        "email": "bob.m@example.com",
        "text": """Bob Martinez
Full Stack Developer | bob.m@example.com

EXPERIENCE

Full Stack Developer — Local Startup (2021-2024)
- Built web applications using React and Node.js
- Some backend work with Python Flask for internal tools
- Used MySQL for database, basic Redis for sessions
- Deployed to AWS EC2 instances

Junior Developer — Freelance (2019-2021)
- Built WordPress sites for small businesses
- Created simple REST APIs with Express.js
- Basic HTML/CSS/JavaScript work

EDUCATION
Bootcamp Certificate, General Assembly (2019)

SKILLS
JavaScript, React, Node.js, HTML/CSS, MySQL, basic Python, AWS EC2""",
    },
    {
        "id": RESUME_IDS[2],
        "name": "Carol Davis",
        "email": "carol.d@example.com",
        "text": """Carol Davis
Backend Engineer | carol.d@example.com

EXPERIENCE

Backend Engineer — Netflix (2019-2024)
- Developed microservices in Python and Java for content recommendation pipeline
- Managed PostgreSQL databases with complex query optimization
- Built real-time data pipelines with Apache Spark and Kafka
- Experience with Docker containerization but limited Kubernetes exposure
- Contributed to open source Python libraries for data processing

Software Engineer — IBM (2016-2019)
- Built enterprise APIs with Django REST Framework
- Worked on legacy system modernization (monolith to microservices)
- Redis usage for distributed caching and rate limiting

EDUCATION
MS Computer Science, MIT (2016)
BS Computer Science, UC Berkeley (2014)

SKILLS
Python, Java, Django, PostgreSQL, Redis, Docker, Kafka, Spark, REST APIs""",
    },
]


async def seed() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if tenant already exists
        result = await session.execute(select(Tenant).where(Tenant.id == TENANT_ID))
        if result.scalar_one_or_none():
            print("Seed data already exists. Skipping.")
            await engine.dispose()
            return

        # Insert tenant first (FK dependency)
        session.add(Tenant(id=TENANT_ID, name="Demo Company", plan="standard", llm_budget=1000))
        await session.flush()

        # Insert job
        session.add(Job(
            id=JOB_ID,
            tenant_id=TENANT_ID,
            title="Senior Backend Engineer",
            description=JOB_DESCRIPTION,
            requirements=["Python", "PostgreSQL", "Redis", "Docker", "Kubernetes"],
        ))

        # Insert resumes
        for r in RESUMES:
            session.add(Resume(
                id=r["id"],
                tenant_id=TENANT_ID,
                candidate_name=r["name"],
                email=r["email"],
                raw_text=r["text"],
            ))

        await session.commit()

    await engine.dispose()

    # Generate JWT token for testing
    token = jwt.encode(
        {"tenant_id": str(TENANT_ID), "sub": "demo-user", "role": "admin"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    print("=" * 60)
    print("Seed data inserted successfully!")
    print("=" * 60)
    print()
    print(f"Tenant ID:  {TENANT_ID}")
    print(f"Job ID:     {JOB_ID}")
    print(f"Resume IDs: {', '.join(str(r) for r in RESUME_IDS)}")
    print()
    print(f"JWT Token:  {token}")
    print()
    print("Test with:")
    print(f'  export TOKEN="{token}"')
    print()
    print("  # List jobs")
    print('  curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/jobs | python -m json.tool')
    print()
    print("  # List resumes")
    print('  curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/resumes | python -m json.tool')
    print()
    print("  # Trigger screening")
    print(f'  curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"job_id": "{JOB_ID}"}}\' \\')
    print("    http://localhost:8000/api/v1/screen | python -m json.tool")


if __name__ == "__main__":
    asyncio.run(seed())
