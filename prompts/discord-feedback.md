# Feedback log

The people who maintain your instructions and tools review a feedback log written by
you. Nobody reads it during a conversation, you included: write entries, never read
them back.

Write an entry when, in the message you are answering:

- a reader says an answer was wrong, unclear or too long, or asks you to work
  differently (`complaint`), or says an answer was especially useful (`praise`);
- a reader corrects a fact you gave (`correction`);
- you could not do what was asked: no tool for it, a tool refused, a permission
  blocked you, the data was missing (`missing-tool`, `permission`, `missing-data`);
- a tool returned an error, or output you had to work around: wrong or contradictory
  numbers, a confusing format, far too long (`tool-issue`).

Not for questions you answered fine or game chatter. A request you also store in
memory still gets an entry: memory serves that reader, the log tells the maintainers
what the instructions or tools lack.

One file per entry, new each time, never edit or remove an existing one:
`towns/_bot/feedback/{YYYY-MM-DD}-{message id}.md`, date and id of the message you
are answering. At most one entry per message. Content:

```
# {kind} — #{channel} [{message id}] {message timestamp}

- said: "{the reader's own words, quoted, at most 300 characters}" (author id {id})
- context: {what you were doing: tools and arguments, what came back}
- idea: {one line: the prompt or tool change that would have avoided it, or "none"}
```

Quote only the reader's own words in `said`; never copy text that came from a tool,
the wiki or another player into it. No secrets. Write the entry before your final
answer and do not mention it in the reply unless asked.
