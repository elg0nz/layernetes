---
title: "Introducing Layernetes: `git push` your AI agents"
date: 2026-07-07
authors: layernetes
excerpt: "Standing up the infrastructure to host an AI agent takes weeks. Layernetes takes one command and about a minute: your agent goes live at a public URL, ready to share, demo, or hand to Claude. Here's how it works, and how to try it."
---

You built an agent. It works. It runs on your laptop, which is exactly where no one else can use it.

That's the wall everyone hits. Building the agent got easy; your coding assistant does most of the typing now. Getting it in front of anyone else is the part that still eats your calendar. Do it yourself and you're wiring up a container, a server, secrets that can't live in your repo, a domain, and TLS, then gluing it all together. Call it a week if you know exactly what you're doing. A month if you're learning it as you go. And you get to do it again for the next agent.

Layernetes collapses all of that into one command. You write your agent, run it, and about a minute later it's live on the internet at its own address.

```sh
llnate push
```

`push` prints a public URL. Send it to a friend, drop it in a channel, put it on screen at demo night, or hand it to Claude. Whoever opens it is talking to your agent.

Weeks of infrastructure, or one command. That's the whole pitch.

## From an idea to a link you can share

Here's the whole path, start to finish:

```sh
llnate init my-agent      # start a new agent project
cd my-agent
llnate plugin install     # bring your AI coding assistant into the loop
# ... build your agent, the way you build everything now ...
llnate login              # sign in to the cloud
llnate keys               # add your API keys, encrypted
llnate push               # ship it, get your URL
```

You spend your time on the middle line, building the agent. Everything around it is one word each. Your agent needs API keys to do its job; `llnate keys` encrypts them so they're safe to keep in your project, and only your running agent can ever read them. You never paste a secret into a dashboard.

When `push` finishes, it hands you the link:

```
Agent is live:
  https://3f2a91c.agents.layernetes.learninglayer.ai
```

That link is real, public, and yours.

## What a live agent gets you

A URL changes what your agent is. On your laptop it's a script only you can run. Live, it's something other people and other agents can reach.

- **Demo it.** Put the link on screen. No "let me just run it locally," no screen-share of your terminal. It works from anyone's phone.
- **Share it.** Send the URL to a collaborator and they're using your agent a second later. Nothing to install on their end.
- **Let Claude use it.** Point Claude, or any MCP client, at the URL and your agent shows up as a tool it can call. Your agent becomes something other agents reach for.
- **Version it by default.** Every push gives you a fresh URL named for the exact code you shipped, so you always know which one you handed out.

## What happens when you push

`llnate push` feels like sending code to GitHub. On the other side, something picks it up and does that week of work for you, in order: it packages your agent, gives it its own address on the internet, unlocks your encrypted keys, and switches it on. Each agent lands in its own sealed space, so yours and everyone else's never touch. From that one address it answers over both plain HTTP and MCP, which is why a browser, a teammate, and Claude can all reach it the same way.

Two details are worth a double-take. Your API keys are unlocked only in memory, at the instant your agent starts, so nothing else can read them: not a file, not a dashboard, not you with a terminal open. And the URL you get back is a fingerprint of the exact code you shipped, so every version has its own unambiguous address.

Here's the part that stops people mid-sentence: none of this runs on a hyperscaler. Your agent goes live on a rack of Dell OptiPlex machines in the 10th Floor Annex. Actual hardware, humming a few floors up, that you can walk over and put your hand on. When we say our own cloud, we mean the literal rack. You can come visit it.

That's the shape of it. How it actually pulls this off is the genuinely interesting part, and it's all open to read in the [repo](https://github.com/elg0nz/layernetes). You never have to touch any of it, and that's the point: the machinery is ours to run, the one command is yours.

## Try it

Layernetes is built by [Sanscourier.ai](https://sanscourier.ai) for members of [Learning Layer](https://www.learninglayer.ai/)'s AI floor. For now, it's members only. If you want to ship agents this way:

1. Become a member at [Frontier Tower](https://frontiertower.io) and join the AI floor.
2. Email [business@sanscourier.ai](mailto:business@sanscourier.ai) for access.

Then it's the five commands above, and your agent is live. Come build with us, and come see the rack it runs on.
