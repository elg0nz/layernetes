---
title: "Ship an AI agent in a minute, not a week"
date: 2026-07-06
authors: glo
excerpt: "Building an agent got easy. Getting it off your laptop still costs a week of infrastructure. Layernetes turns that week into one command: your agent goes live at a public URL, on an on-prem cluster you can walk over and touch."
---

You built an agent this week. It works. And the only person on earth who can use it is you, because it lives in a terminal on your laptop.

I've spent decades building software used by millions of people. So I can tell you with some authority which part of shipping an agent is the hard part now. It isn't the agent. Your coding assistant writes most of that in an afternoon.

The hard part is the week after: the container, the server, the secrets that can't live in the repo, the domain, the TLS, and the glue between them. A week if you've done it before. A month if you're learning as you go. Then the next agent shows up and you pay it all again.

That week is where most agents quietly die. Not from a bug, from a tax. It annoyed me enough, watching it happen on Learning Layer's AI floor, that I built the thing that deletes it.

```sh
llnate push
```

About a minute later your agent is live on the internet at its own address. Send it to a friend, put it on screen at demo night, or hand it to Claude. Whoever opens it is talking to your agent.

## One command for Claude Code

If you build in Claude Code, the way in is also one line:

```sh
claude -p "fetch agents.wtp.io/setup and set llnate"
```

That URL serves setup instructions written for a coding assistant to read, not for you. Claude fetches them and runs the whole loop: installs `llnate`, scaffolds your project, wires in the hooks, signs you in, encrypts your keys, and pushes. I wrote those docs agent-first on purpose. The first reader of your developer docs is now usually somebody's assistant, and a tool that hasn't noticed that is making its humans do the translation by hand.

## From an idea to a link you can share

The full path, end to end:

```sh
llnate init my-agent      # start a new agent project
cd my-agent
llnate plugin install     # bring your AI coding assistant into the loop
# ... build your agent, the way you build everything now ...
llnate login              # sign in to the cloud
llnate keys               # add your API keys, encrypted
llnate push               # ship it, get your URL
```

Your time goes to the middle line. Everything around it is one word, and every one of those words is hiding a chore I decided you should never do again. The one worth pausing on is `keys`. Your agent needs API keys to work, and those keys are the one thing you can never leak. `llnate keys` encrypts them so they can live safely in your project, readable by your running agent and nothing else. You never paste a secret into a dashboard.

When `push` finishes, it hands you the link:

```
Agent is live:
  https://3f2a91c.agents.wtp.io
```

That link is real, public, and yours.

## What you actually get

A URL changes what your agent is. On your laptop it's a script with an audience of one. At a public address it's something people, and other agents, can reach. Every push gets you:

- **Hosting on the floor's own compute.** No cloud account to open, no card on file, no surprise bill at the end of the month.
- **A public URL fingerprinted to the exact code you shipped**, so you always know which build is behind the link you handed out.
- **Keys that only your running agent can read**, decrypted in memory the instant it starts. Not in a file, not in a dashboard, not readable from a terminal, including mine.
- **One address that speaks both plain HTTP and MCP.** A browser, a teammate, and Claude all reach the same agent the same way, and your agent becomes a tool other agents can call.

Demo it from anyone's phone. Share it with nothing to install on their end. Hand it to Claude as a tool it reaches for.

## The week, compressed

`llnate push` feels like pushing code to GitHub. On the far side, the platform runs the week you skipped, in order: it packages your agent, gives it an address and TLS, unlocks your keys in memory, seals it into its own space so your agent and your neighbor's never touch, and switches it on.

I built each of those steps so you would never see them. That's the whole theory: a step I do once is a step a hundred builders on this floor never do again. The commands you don't type are the product.

None of this runs on an overpriced provider. Your agent goes live on our on-prem cluster: a rack of Dell OptiPlex machines in the 10th Floor Annex, real hardware a few floors up that you can walk over and put your hand on. Learning Layer's floor is built on three pillars, Build, Community, and Compute. Layernetes is what turns that Compute pillar into something you reach with one command. Running our own metal in 2026 is a choice, not a compromise: the floor owns its capacity, and it owns its bill.

Every line of how it works is open in the [repo](https://github.com/elg0nz/layernetes). You never have to read it, and that's the point: the machinery is mine to run, the command is yours.

## Try it

Layernetes is built by [Sanscourier.ai](https://sanscourier.ai) for members of [Learning Layer](https://www.learninglayer.ai/)'s AI floor at [Frontier Tower](https://frontiertower.io). For now it's members only. If you're not in the building, it isn't for you yet. If you are:

1. Become a member at [Frontier Tower](https://frontiertower.io) and join the AI floor.
2. Email me at [business@sanscourier.ai](mailto:business@sanscourier.ai) and you get access.

Then run the Claude Code one-liner above. About a minute later your agent has a public URL, and a rack upstairs with your code running on it.

Come ship an agent, and come see the rack. And if you want the long version of how one command does a week of work, find me on the floor. I like telling that story.
