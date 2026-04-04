"""Seed default data.

Revision ID: 002_seed_data
Revises: 001_initial_schema
Create Date: 2024-01-01 00:01:00.000000

This migration seeds default prompts, response formats, folders, and admin user.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '002_seed_data'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed default data."""
    
    # Admin user (username: admin, password: Admin@123)
    op.execute("""
        INSERT INTO users (email, name, role, is_approved, auth_provider, password_hash)
        VALUES (
            'admin',
            'Administrator',
            'admin',
            true,
            'credentials',
            '$2b$10$zK7gvKDxbH5QYDY/8LeajOcjBalWT1CxC1c3hb5ItsF4E1H/ST9bq'
        )
        ON CONFLICT (email) DO NOTHING;
    """)
    
    # Default prompt folder
    op.execute("""
        INSERT INTO prompt_folders (user_id, name, is_default)
        VALUES (NULL, 'Default', true)
        ON CONFLICT DO NOTHING;
    """)
    
    # Default response formats
    op.execute("""
        INSERT INTO response_formats (user_id, name, description, template_text, is_default) VALUES
        (NULL, 'Structured XML', 'Headings, subheadings, bold, bullet/numbered lists wrapped in XML tags', 
        'Format your response using these rules:
1. Wrap your entire response in <response></response> tags.
2. Use <heading>Text</heading> for main headings.
3. Use <subheading>Text</subheading> for sub headings.
4. Use <bold>text</bold> for emphasis.
5. Use "- Item" for bullet lists.
6. Use "1. Item" for numbered lists.
7. Plain text paragraphs separated by blank lines.
Do NOT use markdown.', true),

        (NULL, 'Plain Bullets', 'Simple bullet-point output', 
        'Format your response as a clean bullet-point list:
1. Wrap your entire response in <response></response> tags.
2. Use "- " prefix for every point.
3. Group related points under a label line ending with a colon.
4. No markdown, no HTML except the response tags.', true),

        (NULL, 'Numbered List', 'Sequentially numbered items', 
        'Format your response as a numbered list:
1. Wrap your entire response in <response></response> tags.
2. Number every item sequentially: 1. 2. 3. etc.
3. Group items under topic labels using <heading>Topic</heading>.
4. No markdown.', true),

        (NULL, 'Table Format', 'Pipe-delimited table rows', 
        'Format your response as a table:
1. Wrap your entire response in <response></response> tags.
2. Use pipe-delimited rows: | Column1 | Column2 | Column3 |
3. First row is the header. Second row is separator: | --- | --- | --- |
4. Use <heading>Section</heading> above each table if multiple tables.
5. No markdown.', true),

        (NULL, 'Q&A Format', 'Question and Answer pairs', 
        'Format your response as Q&A pairs:
1. Wrap your entire response in <response></response> tags.
2. Each question: <bold>Q: question text</bold>
3. Each answer on the next line: A: answer text
4. Leave a blank line between Q&A pairs.
5. Group under <heading>Topic</heading> headings.
6. No markdown.', true)
        ON CONFLICT DO NOTHING;
    """)
    
    # Default prompts
    op.execute("""
        INSERT INTO prompts (user_id, name, text, is_default, folder_id) VALUES
        (NULL, 'One-Liner Questions', 
        'Create many, many questions of one line from this Chapter, PDF. One-liner questions, so cover all the concepts and topics and subtopics of this chapter. All the questions, those are possible from this chapter, those answers can be given in one word or one line. You should write down, cover every concept, every topic, and every subtopic, everything from the whole chapter, read it deeply and make as many as questions possible from this Chapter. Write in the end some HOT and Long Questions also List of topics and subtopics to be covered, mapping of all the concepts of the chapter. write in a very compact way, every topic and subtopics in one line with arrow like a flow chart what students will learn in this in this chapter.',
        true, (SELECT id FROM prompt_folders WHERE is_default = true LIMIT 1)),

        (NULL, 'Hindi-English Glossary', 
        'Now Make a long simple list with compact formating print friendly saving space & very compact info, on sheet of all the words of this chapter, these words in Simple English and also in Hindi in one line both, so that students understand these words, terms, concepts, deeply and clearly. For the Students of Hindi Speaking background..format is fine, make a list of words, under topics and subtopics of the chapter, don''t left any hard word undefined.',
        true, (SELECT id FROM prompt_folders WHERE is_default = true LIMIT 1)),

        (NULL, 'Visual Concept Maps (English)', 
        'Now Create visual maps not image based on arrow concepts maps of the all topics and subtopics including all paragraphs of all topics and subtopics, all concepts must be covered, full of emojis and pics and make it easy for students to retain, arrow concept maps of all paragraphs under topics and subtopics with lots of emojis to make visual notes of the chapter for better memory retain and understanding write more and more in one line only, do minimum line breaks, as minimum as possible.',
        true, (SELECT id FROM prompt_folders WHERE is_default = true LIMIT 1)),

        (NULL, 'Bilingual Emoji Concept Map', 
        'bilingual English + Hindi emoji concept map version.',
        true, (SELECT id FROM prompt_folders WHERE is_default = true LIMIT 1)),

        (NULL, 'Facts & Data List', 
        'All Facts, Important data, make a long list under topics and subtopics, Name of concept, place, Person, some date, important event and some ranking, where, what, which position, rankings, personality, invention all different kind of all possible facts of the chapter under all topics and subtopics. Make a simple print friendly list with emojis. Lots of facts in form of a simple list.',
        true, (SELECT id FROM prompt_folders WHERE is_default = true LIMIT 1)),

        (NULL, 'Real-World Projects & Problems', 
        'Now Create many many real life Project and real life Problems to solve students so that they can develop problem solving skills, so that they can deeply develop different types of thinkings. Many many small or big problems based on all the subtopics and topics and every concept they have learned so far. I want to connect learning to real life and develop thinking skills and other 21st century skills. Create problems under topics and subtopics but also write which skill will develop or targeted skill for the problem children are solving, for all thinking types: Critical Thinking, Analytical Thinking, Creative Thinking, Divergent Thinking, Convergent Thinking, Logical Thinking, Concrete Thinking, Abstract Thinking, Reflective Thinking, Systems Thinking, Intuitive Thinking, Deductive Thinking, Inductive Thinking, Lateral Thinking, Emotional Thinking.',
        true, (SELECT id FROM prompt_folders WHERE is_default = true LIMIT 1)),

        (NULL, 'Life-Changing Concepts', 
        'NOW MAP THE big concepts which we want that student must carry in their hearts and brains after doing this chapter. Concepts which can bring Behavioural change. Life Changing concepts, concepts that can change attitude of the child. Major Concepts they must develop after doing this chapter so that I can do the Assessment based on Life transformation of the child after learning all the above chapter. So make a list of these Life Changing concepts from this chapter affecting behaviour, attitude, life, must become life long learning after this chapter. Map the concepts against skills which can be acquired and life long learning ideas and principals to live now onwards. Make a solid list of these deep life changing concepts for the child assessment.',
        true, (SELECT id FROM prompt_folders WHERE is_default = true LIMIT 1))
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    """Remove seeded data."""
    op.execute("DELETE FROM prompts WHERE is_default = true")
    op.execute("DELETE FROM response_formats WHERE is_default = true")
    op.execute("DELETE FROM prompt_folders WHERE is_default = true")
    op.execute("DELETE FROM users WHERE email = 'admin'")
