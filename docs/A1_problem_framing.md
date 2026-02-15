# A1 -- Problem Framing: AI Resume Screening Tool

## Who is the user?

HR recruiters and hiring managers at companies using our B2B SaaS platform.
These are non-technical users who review 50-200+ resumes per open role. They need
to shortlist candidates quickly without missing strong applicants buried in the stack.

## What decision are they trying to make?

"I think the time to spending to Screening Interview is take too long and i think this process can using ai to help reduce time and improve accuracy"

They need:
- A ranked list of candidates scored against a specific job description
- A plain-English summary of why each candidate scored high or low
- Confidence that the tool isn't silently filtering out good candidates
- Alignment of candidate skill with job requirements
- Alignment of candidate experience with job requirements
- we will create rule of thumb for filtering candidates

## Why a rule-based system is insufficient

1. **Job descriptions are unstructured natural language.** A rule engine would need
   hand-coded keyword lists per role. "5+ years of Python" vs "extensive Python
   experience" vs "senior Python developer" all mean similar things but fail exact match.

2. **Resumes are wildly inconsistent.** Different formats, section names, phrasing.
   One candidate writes "Led a team of 8" while another writes "Engineering Manager,
   direct reports: 8". Regex/keyword extraction breaks constantly.

3. **Skill inference matters.** A candidate listing "Built real-time data pipelines
   with Kafka and Spark" implies distributed systems experience even if they never
   use that phrase. LLMs handle this semantic reasoning; rules cannot.

4. **Context-dependent scoring.** "3 years experience" is strong for a junior role
   but weak for a staff role. The scoring logic must adapt to each job description's
   requirements -- this is where LLM judgment excels over static rules.

5. **Explainability requirement.** Business users need to understand *why* a candidate
   scored 82/100. LLMs can generate structured reasoning that maps back to specific
   JD requirements. A rule engine's "matched 6/10 keywords" is not actionable.
