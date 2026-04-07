import sys
sys.path.insert(0, '.')
from app.services.document_export import create_docx

content = '''<title>Home Play Activities</title>
<instruction>Fun, hands-on activities to do at home with your family. No boring homework — just playful learning!</instruction>
<hr/>

<box title="Activity 1: Water Hunt at Home">
<bold>What to Do:</bold>
Walk around your home with a parent and find all the places where you use or see water. Look in the kitchen, bathroom, balcony, and garden. For each place, talk about where that water may come from.
Draw or list your finds together.

<bold>Materials Needed:</bold> Paper, pencil, crayons
<bold>Concept Tested:</bold> Places where water is found; sources of water in daily life
<bold>Parent's Role:</bold> Help the child observe different areas of the home and discuss possible water sources.
<bold>Learning Outcome:</bold> The child identifies water in everyday surroundings and connects it to its source.
</box>

<hr/>

<box title="Activity 2: Trace the Tap Game">
<bold>What to Do:</bold>
Choose one tap in the house. Trace the path of the water backwards by asking, "Where does this water come from?" Keep tracing clues to a tank, pipe, tanker, well, or other source.
Draw a simple arrow map of the water path.

<bold>Materials Needed:</bold> Paper, pencil, colors
<bold>Concept Tested:</bold> Water paths; tap water coming from natural and human-made sources
<bold>Parent's Role:</bold> Ask guiding questions like "What is behind this tap?" and help the child make a simple map.
<bold>Learning Outcome:</bold> The child understands that tap water comes through pipes, tanks, or tankers from natural sources.
</box>

<hr/>

<box title="Activity 3: Natural or Human-Made Sorting Game">
<bold>What to Do:</bold>
Collect or name water sources such as river, lake, pond, sea, well, hand pump, and dam. Sort them into two groups: natural sources and human-made sources.
Make it into a quick game by taking turns calling out one source at a time.

<bold>Materials Needed:</bold> Small paper slips or cards, pen, two bowls or two paper circles
<bold>Concept Tested:</bold> Classification of water sources into natural and human-made
<bold>Parent's Role:</bold> Say the names of the water sources, check answers, and correct gently if needed.
<bold>Learning Outcome:</bold> The child can tell the difference between natural and human-made water sources.
</box>'''

results = [{'prompt_name': 'Home Play Activities', 'content': content}]
buf = create_docx('Home Play Activities', results)
with open('test_box_spacing.docx', 'wb') as f:
    f.write(buf)
print('Created test_box_spacing.docx')
