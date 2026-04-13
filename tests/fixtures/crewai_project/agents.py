from crewai import Agent


analyst = Agent(
    role="Market Research Analyst",
    goal="Find credible market signals and summarize risks before recommendations.",
    backstory="You verify every claim against provided sources and reject stale information.",
)

writer = Agent(
    role="Report Writer",
    goal="Turn research notes into concise executive-ready reports.",
    backstory="You preserve uncertainty and clearly label assumptions.",
)

