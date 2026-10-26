# Mockup walkthrough (Phase 0)

A 20–30 minute moderated session with a target user on the clickable prototype in [`design/prototype/index.html`](../../design/prototype/index.html). The goal is to find friction before any app code exists.

## What the prototype is

- Two sample courses (Intro Psychology, Cell Biology) with sample textbook passages. Page numbers are illustrative.
- Everything is simulated in the browser: card generation, file processing and chat answers. Chat only knows a handful of topics. Anything else shows the "not in your materials" label, which is also worth testing.
- Nothing is saved. "Start over" in the sidebar resets it between sessions.

## Running the session

- Use the participant's own laptop and browser if possible.
- Ask them to think aloud. Then stay quiet: don't explain the UI, don't point, don't rescue. If they're stuck for more than a minute, note it and move to the next task.
- Read each task as written. The tasks describe goals, never the buttons.
- Write down every hesitation, wrong click, "what does this mean?", and anything they say they like.

Have a PDF and an image file on the desktop for task 6.

## Tasks

| # | Read this to the participant | Watch for |
|---|---|---|
| 1 | "You've got 10 minutes to study. Go ahead." | Do they find and start the review without hesitating? |
| 2 | "Work through your cards." (Let them do 3–4.) | Do they understand Forgot / Hard / Got it / Easy? Do they find the keyboard shortcuts on their own? Is auto-grading on multiple choice clear? |
| 3 | "Where did that answer come from?" | Do they notice the source panel? Do they open the full page? |
| 4 | "Say you think one of these cards is wrong. What would you do?" | Do they find the report option? Are the three reasons clear? |
| 5 | "Your Psychology class just finished Chapter 4. Let the app know." | Do they find the course page and the "We've covered this" button? Is "new cards tomorrow" clear or disappointing? |
| 6 | "Your lecturer posted this week's slides. Add them." | Drag and drop or click? Do they understand the "reading it now" state? |
| 7 | "Something from your last lecture confused you. Get some help with it." | Do they find Ask? Do they click citations? How do they react to the "not in your materials" label? |
| 8 | "When is your next Biology test?" | Is the exam date easy to find? |

## Debrief questions

1. What was the most confusing moment?
2. Is there anything you expected to be there that wasn't?
3. Would you use this instead of what you do now? What would stop you?
4. Rating buttons: did the labels and the "in 3 days" hints make sense?
5. Multiple choice graded itself, while other cards asked you to rate yourself. Did that feel inconsistent?
6. How would you feel about a daily reminder: useful, or annoying?

## Open design questions this session should answer

- Self-rating with four buttons vs. a simpler two (Forgot / Got it).
- Whether new cards should appear in today's review or start tomorrow.
- Whether "We've covered this" is the right trigger, or whether slides should also produce cards on their own.
- Whether the source panel helps or is noise while reviewing.

## Findings

Record findings in [`docs/ROADMAP.md`](../ROADMAP.md) under Phase 0, with each one turned into a decision or a change to the mockups.
