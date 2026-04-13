from crewai import Task


collect_competitors = Task(
    description="Collect competitor positioning, target customers, and notable pricing changes.",
    expected_output="A structured competitor table with source notes.",
)

draft_report = Task(
    description="Draft a market summary with risks, opportunities, and recommended next steps.",
    expected_output="A concise markdown brief for leadership review.",
)

