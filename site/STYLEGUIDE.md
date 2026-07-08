# Layernetes Copy Style Guide

How we write the site, the docs, the blog, and the CLI output. The goal is copy
that reads like it was written by a builder who respects your time, not a vendor
selling you something. Two references anchor the craft: Stripe (calm, precise,
value-first) and Vercel (terse, confident, present-tense). We take their clarity
and drop their em-dashes.

If you read only one thing: **show the thing working, in as few words as possible,
to someone who already knows the field.**

---

## 1. Who you are writing for

You never name this reader on the page. You write so the page fits them like it was
made for them. Assume the reader:

- **Ships agents for a living.** They use MCP, Docker, git, and a coding assistant
  every day. They have deployed things to production and been burned by the parts
  nobody demos. Never explain what an agent, MCP, or a container is. Defining a term
  they already own reads as an insult and wastes the one thing they guard: attention.
- **Measures progress in things they can show.** Their unit of done is a live,
  shareable artifact they can put in front of peers tonight. Time-to-a-working-URL is
  the benefit that lands. Not "productivity," not "efficiency." A link they can paste.
- **Distrusts polish.** They value "show your work" over closed-door claims. A code
  block that runs beats a paragraph that promises. Receipts over adjectives.
- **Moves fast but wants rigor.** They vibe-code at speed and still care about
  secrets, isolation, and reliability. Never imply fast means sloppy. Show the speed
  and the safety in the same breath.
- **Values open and composable.** Standard protocols, no lock-in, works with the
  tools they already run. Signal interoperability (MCP, HTTP, git-push) plainly.
- **Belongs to a room, not a customer list.** Access is a membership among peers, not
  a pricing tier. Frame inclusion as belonging, never as a discount.

The test for every sentence: *would this survive being read aloud at a demo night,
to a room of people who build this stuff?* If it tells them something they know, or
sounds like a booth banner, cut it.

---

## 2. Voice principles

**Lead with the value, framed as infrastructure.** The H1 is a claim about what the
product *is*, in a confident noun phrase. Stripe: "Financial infrastructure to grow
your revenue." Vercel: "Agentic Infrastructure." Ours: "The cloud for AI agents." The
brand name lives in the nav; the headline does the work.

**Say the smallest true thing.** Every sentence earns its place or it is deleted. No
throat-clearing intro, no "in today's fast-paced world." Open on the point.

**Present tense, active voice, real verbs.** Build. Ship. Push. Deploy. Encrypt. The
reader does the verb; the product gets out of the way. "You write the agent and
push," not "Our platform enables you to deploy."

**Peer voice, not vendor voice.** Write builder-to-builder. Confident, plain, a
little dry. Never breathless. The reader has seen a hundred landing pages; earn trust
by sounding like the person next to them at the coffee machine, not the sponsor.

**Prove, do not promise.** Back a claim with the command, the URL, the actual output.
If you cannot show it, do not claim it. "theory follows practice" is the reader's own
ethos, so a page that demonstrates outranks a page that describes.

**Use an elegant scope device.** State a range to show reach without a stats dump.
Stripe: "from your first transaction to your billionth." Ours: "from your laptop to a
public URL, in one push." One line, and the whole arc is understood.

**Numbers only when real.** Hard metrics are powerful (99.999%, one command, two
protocols) but a fabricated stat detonates trust with exactly this reader. If you do
not have the number, use the concrete mechanic instead. Never invent.

**Calm beats loud.** No hype, no urgency theater, no "revolutionary." Confidence is
quiet. The strongest line on the page should be the plainest.

---

## 3. Structure

A page or section, top to bottom:

1. **H1 / hero.** The value prop as a noun phrase. One supporting sentence that
   expands it in plain language, ideally with the scope device.
2. **CTAs.** Short imperatives. "Get started." "Deploy now." "Read the post." Two or
   three, primary first.
3. **The proof.** The command, the flow, the thing running. Put this high. Show
   before you tell.
4. **Feature cards.** Each is a clean title plus one flat present-tense sentence.
   Name the capability, state what it does, stop.
5. **Where to go next.** Links out to docs, blog, onboarding.

**Section headers are confident complete statements.** "From your laptop to a public
URL, in one push." "Secrets that never leak." Not "Features" or "Benefits."

**Feature pattern:** `Title (verb-or-noun) + one sentence.` End the sentence on the
sharpest word, often with a colon. "One thing can read them: your running agent."

**Show the terminal.** A code block with real commands and real output is worth more
than three paragraphs. This reader reads code faster than prose.

---

## 4. Mechanics

**No em-dashes. No en-dashes as separators.** This is a hard rule (and the house
style across our repos). Replace them:

- Aside or amplification → period or colon. `secrets — encrypted` becomes `secrets,
  encrypted` or a new sentence.
- Range → the word "to". `10–2 minutes` becomes `10 minutes to 2`.
- Parenthetical → parentheses or commas.

**Punctuation is calm.** Periods over exclamation marks. If a line needs a "!" to land,
rewrite the line.

**Oxford comma, sentence case in headers, American spelling.**

**Second person.** "You," not "the user" or "developers."

**Contractions are fine.** They keep the peer voice. "It's live," not "It is live,"
unless the rhythm wants the full form.

**CLI output is copy too.** The strings `llnate` prints follow this guide: terse,
present-tense, honest. `push` narrating "phase: Deploying" then printing the URL is
on-brand. A cheerful "🎉 Success!!!" is not.

---

## 5. Word list

Avoid. These are vendor tells that this reader has learned to skim past:

`seamless`, `effortless`, `revolutionary`, `game-changing`, `cutting-edge`,
`unleash`, `empower`, `supercharge`, `next-gen`, `robust`, `world-class`,
`simply` / `just` used to wave away real work, `blazingly fast`, `magic` (unless you
then show the mechanism), any exclamation-mark enthusiasm.

Prefer. Say the concrete thing:

`live`, `public URL`, `one command`, `in memory`, `ciphertext`, `callable`,
`ships with`, `git push`, `already runs`, `before the coffee's done`. Verbs and
nouns the reader can picture.

Never reintroduce implementation trivia as if it were the pitch. The framework, the
host machine, the internal plumbing are answers to "how," not the headline. Lead with
what the reader gets; let the mechanics be the reward for reading on.

---

## 6. Before and after

Real edits from this site, showing the rules in motion.

> ~~Build, ship, and host CrewAI-powered agents that run on your laptop.~~
> **The cloud for AI agents.**

Cut the framework and the host detail (trivia, not value). Reframed as infrastructure.

> ~~No AWS account, no infra to run. It isn't for rent.~~
> **No AWS account, no infra to run. The platform comes with your membership.**

"For rent" is a landlord's metaphor; the reader is a builder, not a tenant. Reframed
as belonging.

> ~~One command takes you from local crew to a live agent — deploy streams progress.~~
> **One command takes local code to a live, public URL. Deploy streams progress.**

Killed the em-dash. Made the payoff concrete ("public URL").

> ~~Credentials are decrypted at startup and are only available to your agent.~~
> **Your API keys are decrypted in memory at startup. One thing can read them: your
> running agent.**

Same fact, but it ends on the sharpest word and reads like a person, not a datasheet.

---

## 7. Checklist before you ship copy

- [ ] The H1 states what the product is, not what the company does.
- [ ] Nothing on the page explains a term this reader already owns.
- [ ] The benefit is something they can see or show, stated in a concrete noun.
- [ ] There is a runnable command or real output above the fold of the argument.
- [ ] Every claim is something the product literally does.
- [ ] Zero em-dashes. Zero exclamation-mark hype. Zero banned words.
- [ ] Headers are confident statements, not labels.
- [ ] Read it aloud. If a sentence sounds like a booth banner, or tells the reader
      something obvious, delete it.
