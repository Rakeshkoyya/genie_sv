import sys
sys.path.insert(0, '.')
from app.services.document_export import create_docx

content = '''<box title="Activity 1: Handspan Hunt">
<bold>What to Do:</bold>
Choose 3 small objects at home, like a book, a spoon, and a pillow. Measure each object using your handspan. Ask another family member to measure the same objects with their handspan and compare the results. Talk about why the numbers are different.

<table>
<row><cell><bold>Materials Needed</bold></cell><cell>Book, spoon, pillow, notebook, family members hands</cell></row>
<row><cell><bold>Concept Tested</bold></cell><cell>Non-standard units of length; why body-part units differ from person to person</cell></row>
<row><cell><bold>Parents Role</bold></cell><cell>Help the child measure safely, compare the results, and ask why the answers are not the same</cell></row>
<row><cell><bold>Learning Outcome</bold></cell><cell>The child understands that handspan is not a reliable unit for everyone</cell></row>
</table>
</box>

<box title="Activity 2: Find the Right Tool">
<bold>What to Do:</bold>
Look around the house and choose 3 things to measure: a pencil, a table, and a scarf or belt. Pick the best measuring tool for each one.

<table>
<row><cell><bold>Materials Needed</bold></cell><cell>Pencil, table, scarf, small scale, metre scale, measuring tape</cell></row>
<row><cell><bold>Concept Tested</bold></cell><cell>Choosing correct tools for measurement</cell></row>
</table>
</box>'''

results = [{'prompt_name': 'Activities', 'content': content}]
buf = create_docx('Box Table Test', results)
with open('test_box_table.docx', 'wb') as f:
    f.write(buf)
print('Created test_box_table.docx')
