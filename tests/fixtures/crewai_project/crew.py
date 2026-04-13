from crewai import Crew

from agents import analyst, writer
from tasks import collect_competitors, draft_report


crew = Crew(
    agents=[analyst, writer],
    tasks=[collect_competitors, draft_report],
    process="sequential",
)

