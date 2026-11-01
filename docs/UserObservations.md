# User observations (Phase 1 exit)

A moderated session with a target user on the deployed app (https://engramstudy.app), on
their own laptop and account. Its findings drive Phase 2's redesign of the core flows.

Record behaviour and quotes about the product only. No names, schools or anything else that
identifies the participant: this file is public.

## Running the session

- Think aloud; then stay quiet. Don't explain the UI, point, or rescue. After a minute
  stuck, note it and move on.
- Read each task as written. The tasks describe goals, never buttons.
- Note every hesitation, wrong click, "what does this mean?", and anything they like.
- Have one chapter's worth of real course material ready (textbook PDF or lecture slides).

## Tasks

| #   | Read this to the participant                                      | Watch for                                                                             |
| --- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| 1   | "This is Engram. Take a look around."                             | Time to get oriented; what they notice first (the Phase 0 bar is under 5 s, D21)      |
| 2   | "Add the material for one of your courses."                       | Do they find upload? Is the "reading it" state clear while it processes?              |
| 3   | "Your class has covered this chapter. Let Engram know."           | Do they find "We've covered this"? Is the wait for cards clear or frustrating?        |
| 4   | "You've got 10 minutes to study. Go ahead."                       | Do they find the review at once? Ratings, keyboard shortcuts, multiple choice grading |
| 5   | "Where did that answer come from?"                                | Do they open the source? Does the highlighted page help?                              |
| 6   | "Say you think one of these cards is wrong. What would you do?"   | Do they find the flag? Are the reasons clear?                                         |
| 7   | "Something from the chapter confused you. Get some help with it." | Do they find Ask? Do they click citations? Reaction to "not in your materials"        |
| 8   | "You have a test coming up. Add it, with the chapters it covers." | Quick-add, picking a day, the chapter picker; is the date then visible on Today?      |

## Debrief questions

1. What was the most confusing moment?
2. Was anything missing that you expected to be there?
3. Were the cards good: right length, right difficulty, worth remembering?
4. Would you use this every day instead of what you do now? What would stop you?
5. How did it feel on your laptop: text size, speed, the wait after uploading?

## Observations

| Task | What happened                                             | Quote or note                                                                                                                                 |
| ---- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Took less time, too little to measure accurately (~3-4 s) | This is obviously because there is far less on screen compared to the demo.                                                                   |
| 2    | Class material was added without an issue                 | There was a glitch with modal and the worker stopped. Heartbeat fix is done, but because of that we switched to localhost for remaining tests |
| 3    | Mark chapter as covered worked.                           | Wait for cards was clear, a little boring. Probably adding some fun animations/motion would help with that.                                   |
| 4    | Review found immediately, everything went smoothly        | Already familiar with the demo, this went without any hitches.                                                                                |
| 5    | Sources were found quickly.                               | "This is really useful" - the tester.                                                                                                         |
| 6    | Flag was obvious and clear.                               | "I don't know how often I'd use this" - the tester. Shift it to be a bit more out of the way, rather than directly under evey card?           |
| 7    | Ask was found without an issue with the new navbar        | Tester preferred a topbar rather than the sidebar used in the demo.                                                                           |
| 8    | Hesitated on the calendar; got confused with mm/dd/yyyy   | Change to dd/mm/yyyy (We should have done that from the start). Once selected date was visible.                                               |

## Debrief answers

1. "Nothing really."
2. "Nothing. I like the new calendar." Mentioned that some way to set the "goal" of a session could be nice (general revision/for a quiz/project). We can consider how that might work, I'm not sure.
3. "I liked having all the MCQs at the end" (re: the different types of questions.)
4. "Maybe. I'd have to use it more and decide how useful it is."
5. We have only done Tasks 3-8 on this computer, so this question is still open. The screen is a bit smaller and much lower resolution than mine, and I find this a little big, so we can probably go ahead assuming that this is fine. If something changes we can adjust in phase 2

## Findings

Each finding becomes a decision or a Phase 2 change in [`ROADMAP.md`](ROADMAP.md).

| Finding                                                                                    | Outcome                                                                                                                  |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Oriented in about 3–4 s, but on a sparse account with little on screen                     | Keep the welcome screen (D21); the 5 s bar has to hold on a full Today screen, which the Phase 2 exit session tests      |
| The worker was preempted mid-ingestion and the upload stalled                              | Fixed by renewing the job lock (D51); a stalled or failed job still needs a clear state on screen (Phase 2 error states) |
| The wait for cards was clear but a little boring                                           | Show real progress, the count of cards made so far, with gentle motion that respects reduced-motion settings (D53)       |
| Found the flag at once, but doubted they'd use it often; it sits directly under every card | Move it to a small "Report" control in the card's corner, with a keyboard shortcut (D52)                                 |
| Preferred the top bar to the sidebar used in the demo                                      | Keep the top bar (D50)                                                                                                   |
| Hesitated on the calendar's mm/dd/yyyy date entry                                          | Dates written out ("12 Nov 2026") and entered day/month/year in Engram's own date field (D54)                            |
| "I liked having all the MCQs at the end"                                                   | Blocked order becomes the default; blocked and separate are compared in the first weeks of daily use (D55)               |
| Suggested setting a goal for a session: general revision, a quiz, a project                | Explored in Phase 3 alongside exam focus mode, which is the same idea aimed at a date                                    |
| Text size fine on the tester's laptop, a little large on a higher-resolution screen        | Keep the larger base size; everything is sized relative to it, so a later change is one line                             |
| Sources, review, chat and marking chapters covered all went smoothly                       | Keep as built                                                                                                            |

# Second Round

## Observations

In this round, tests were conducted on the user's machine in the actual app, rather than localhost. Another round was conducted on mobile phone.

### Computer

- UI elements rendered a too large, especially in the review (the 4 options frequently needed scrolling to see)
- Tester mentioned the text describing the Ask page was annoying: "Stuck on something in Biology? Ask in your own words. Answers come from your textbook, slides and notes, with a link to the exact page." was too wordy
  and pointless. No explanation at all would have been better there.
- Tester disliked the citations in the Ask section. Mentioned that opening the relevant textbook page like that didn't help and just made the text harder to read. Re: this, I agree, we should go back to normal citations rather than displaying the textbook page
- There were too many options in the "choose your subjects" in the calendar. For the Biology course, there were 47 chapters, too many to easily pick out a few to choose for a quiz/midterm/etc.

### Mobile (Lower priority but still worth considering)

- On mobile, the topbar wraps around into two rows.
- Card review is hard to do on mobile and the sources become pretty much useless, as you need to scroll down past the 4 options, meaning you can't see what the original card said.
- The ask citations listed above are even worse here, almost completely illegible.
- The too many options problem was even worse here, as the subjects were one per line.
- The calendar was useless, it was spaced too much and needed separate scrolling.
- Responses in chat were too large, became hard to read as so much space was being taken up by the response.

## Findings

Each finding becomes a decision or a Phase 2 change in [`ROADMAP.md`](ROADMAP.md). Rows marked _(screenshots)_ were seen in the mobile screenshots rather than noted during the session.

| Finding                                                                                                                | Outcome                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The interface felt too large on the tester's laptop; in review, the four buttons under the card often needed scrolling | Text size stays; everything around it (spacing, padding, buttons, the card's frame) gets smaller, tuned on the dev server until review fits card and buttons on a 1366×768 screen (D63) |
| The Ask page's intro text was wordy and pointless; no explanation would have been better                               | Remove it; the field's placeholder ("Ask about Biology…") already says what to do (D64)                                                                                                 |
| Opening a citation in Ask showed the textbook page, which didn't help and made the answer harder to read               | A citation opens its passage as text, quoted words marked, with book, section and page above it and a link to the PDF at that page; no page image in Ask (D65)                          |
| The chapter picker listed all 47 chapters of a textbook, too many to find the few a test covers                        | Chapters already covered come first, a "Chapters 3 to 7" range covers the rest, and the full list is one step away (D66)                                                                |
| _(screenshots)_ The chapter picker sits below the Add button                                                           | Move it above Add, so the form reads top to bottom                                                                                                                                      |
| Mobile: the top bar wraps into two or three rows                                                                       | On phones the bar is just the Engram name and a menu button, which opens a sidebar with Today, Calendar, Ask, Admin and Sign out; the top bar stays on wider screens (D67)              |
| Mobile: the source sits below the four ratings, so reading it means scrolling away from the card                       | On phones the ratings are one compact row pinned to the bottom and the source follows the card directly; on wide screens it sits beside the card (D68)                                  |
| Mobile: citations in Ask are almost illegible, a whole textbook page shrunk to the phone's width                       | Solved by passages as text (D65)                                                                                                                                                        |
| Mobile: the chapter picker is one chapter per line                                                                     | Solved by the shorter list (D66), with compact rows on phones                                                                                                                           |
| Mobile: the calendar is too spread out and scrolls sideways on its own                                                 | On phones the month grid gives way to one week at a time: a list of seven days with what's due on each, and previous and next week (D69)                                                |
| Mobile: answers in Ask take up most of the screen                                                                      | Smaller reading size and a one-line "Not from your materials" note on phones                                                                                                            |
| _(screenshots)_ The Ask and Clear buttons squeeze the question field, cutting off its placeholder                      | Send becomes an icon inside the field's edge (Enter still sends) and the field grows to fit longer questions; Clear moves above the conversation as "New question" (D70)                |
| _(screenshots)_ Admin tables run off the side of a phone                                                               | No change: admin is a desktop tool                                                                                                                                                      |
