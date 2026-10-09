---
name: reader-text
description: Write or revise any text a dashboard reader sees, so PEM staff understand it without knowing how the pipeline works.
---
Reader. Sales, planning and management staff at PEM. They know the products and the business. They do not know the code, the files or the project's rule numbers.

Language. Thai. Where a Thai word or sentence would confuse the reader, use the English term or sentence instead and always add a short Thai explanation next to it (for example Relative MAE, Tracking Signal, Naive). Keep terms the team already uses in English as single words: MAE, RMSE, Bias, MASE, PO, Min, Max, MTS, MTO, forecast, not-late.

Keep off screen, move into an HTML comment: file names, code paths, line numbers, METRICS, DATA_MAP or STATUS references, config keys, internal status names such as stock_policy or confirmed_to_order, and explanations of why the data was built the way it was.

Say the current state, not the history. Never write that something was corrected, is no longer typed by hand, or was done as requested. Never use ผู้ใช้ to mean the person who instructed the agent.

One word, one meaning. ตัวเลขสมมติ means made-up figures for illustration. ค่าประมาณจากสูตร means a value computed by formula in place of a real one. แผน means future months in a plan. ตัวอย่าง is used only for a worked reading example in the manual.

Shape of an explanation under a chart: the question the chart answers, then what the X and Y axes are with units, then how to read one value, then what not to conclude. Two to four short lines. Match the style of docs/user_manual.md.

Patterns to remove: the construction ไม่ใช่…แต่เป็น… used for emphasis; a closing line that repeats the section; lists of three for rhythm; long dashes joining clauses, replaced by a full stop or a new line; bold used as decoration; parentheses inside parentheses; one sentence carrying several notes.

Check before finishing: every number in the old text is still present or deliberately moved to a comment; no number was added; no file name or rule number is visible.
