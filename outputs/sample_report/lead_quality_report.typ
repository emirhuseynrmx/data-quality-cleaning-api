#set page(margin: 42pt)
#set text(font: "Arial", size: 10pt)
#set heading(numbering: none)

#let accent = rgb("#1457d9")
#let good = rgb("#11845b")
#let warn = rgb("#b86b00")
#let bad = rgb("#b42318")
#let muted = rgb("#667085")
#let panel = rgb("#f6f8fb")

#let stat(label, value, color: accent) = block[
  #rect(fill: panel, radius: 5pt, inset: 10pt, width: 100%)[
    #text(size: 8pt, fill: muted, weight: "bold")[#upper(label)]
    #linebreak()
    #text(size: 18pt, fill: color, weight: "bold")[#value]
  ]
]

#let bar(label, value, color: accent) = block[
  #text(size: 8pt, fill: muted)[#label]
  #linebreak()
  #rect(width: 100%, height: 7pt, fill: rgb("#e7ebf2"), radius: 3pt)[
    #rect(width: value * 1%, height: 7pt, fill: color, radius: 3pt)
  ]
]

= CRM Lead List Quality Report

#text(fill: muted)[
  Client-ready data hygiene summary for a CRM or spreadsheet import.
  This report shows what changed, what still needs review, and which columns
  are safe enough for automation.
]

#grid(columns: (1fr, 1fr, 1fr, 1fr), gutter: 8pt)[
  #stat("Quality score", "95.1/100", color: good)
][
  #stat("Rows cleaned", "6 -> 5")
][
  #stat("Duplicates removed", "1", color: warn)
][
  #stat("Invalid contacts", "2", color: bad)
]

== Import Readiness

#bar("Overall quality", 95.1, color: good)

#grid(columns: (1fr, 1fr), gutter: 12pt)[
  === Main Warnings
  - email has 1 invalid email values.
- phone has 1 invalid phone values.
][
  === Recommended Actions
  #block(stroke: rgb("#d0d5dd"), radius: 5pt, inset: 7pt)[#text(weight: "bold")[High: Duplicate leads]#linebreak()#text(fill: muted)[Import only deduplicated rows and keep the duplicate export for sales ops review.]]
#block(stroke: rgb("#d0d5dd"), radius: 5pt, inset: 7pt)[#text(weight: "bold")[High: Invalid email values]#linebreak()#text(fill: muted)[Route invalid email rows to manual review before email automation or CRM sync.]]
#block(stroke: rgb("#d0d5dd"), radius: 5pt, inset: 7pt)[#text(weight: "bold")[Medium: Invalid phone values]#linebreak()#text(fill: muted)[Keep cleaned E.164 numbers and request corrected phone values for failed rows.]]
]

== Column Profile

#table(
  columns: (1.4fr, .8fr, .7fr, .8fr, .8fr, .8fr),
  inset: 5pt,
  stroke: rgb("#d0d5dd"),
  [*Column*], [*Type*], [*Confidence*], [*Missing*], [*Invalid*], [*Unique*],
  [email], [email], [75%], [20%], [1], [4],
  [phone], [phone], [80%], [0%], [1], [5],
  [estimated_budget], [text], [100%], [20%], [0], [4],
  [name], [text], [100%], [0%], [0], [5],
  [company], [text], [100%], [0%], [0], [5],
  [source], [text], [100%], [0%], [0], [5],
  [notes], [text], [100%], [0%], [0], [5],
)

== Cleaned Sample

#table(
  columns: (1.1fr, 1.4fr, 1.1fr, 1.2fr),
  inset: 5pt,
  stroke: rgb("#d0d5dd"),
  [*Name*], [*Email*], [*Phone*], [*Company*],
  [Alice Johnson], [alice\@example.com], [+14155550199], [Acme Telecom],
  [Bob Smith], [bad-email], [+14155550188], [Beta Wireless],
  [Nora Lee], [nora\@example.com], [not-a-phone], [Northstar Fiber],
  [Diego Martins], [diego\@example.com], [+12125550144], [MetroNet],
  [Sara Khan], [], [+13125550133], [CloudCell],
)

== Delivery Notes

- Spreadsheet formula prefixes are neutralized before export.
- Email and phone fields are normalized only when they pass format validation.
- Duplicate removal uses the configured key list. For this sample, the key is `email`.
- This API validates and cleans CRM import data. It does not enrich private
  contacts or verify mailbox ownership.
