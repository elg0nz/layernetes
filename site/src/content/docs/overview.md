---
title: Overview
description: What Layernetes is, how to ship an agent, and how it works, in one page.
head:
  - tag: script
    attrs:
      type: application/ld+json
    content: |
      {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
          {
            "@type": "Question",
            "name": "What is Layernetes?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "Layernetes is the Learning Layer cloud for AI agents, built by Sanscourier.ai. You write a CrewAI-powered agent locally, run llnate push, and it goes live at a public URL any human or any AI can call — over MCP or plain HTTP. The source is open under AGPL-3.0-or-later at github.com/elg0nz/layernetes."
            }
          },
          {
            "@type": "Question",
            "name": "How do I deploy an AI agent on Layernetes?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "Six commands: llnate init my-agent scaffolds the project, llnate plugin install brings your AI coding assistant into the loop, you build the agent, llnate login provisions your cloud repo and encryption keys, llnate keys encrypts your API keys into the repo, and llnate push deploys — it blocks until the agent is live and prints its public MCP and HTTP URLs. Agent-readable setup instructions live at layernetes.wtp.io/setup."
            }
          },
          {
            "@type": "Question",
            "name": "How do I call a deployed Layernetes agent from Claude or another MCP client?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "Every deployed agent serves a FastMCP endpoint at /mcp on its public URL. For example: claude mcp add --transport http my-agent https://<sha>.agents.wtp.io/mcp. The same address also answers plain HTTP — POST /kickoff runs the agent, /docs shows the interactive API docs, and GET /healthz reports liveness."
            }
          },
          {
            "@type": "Question",
            "name": "How does Layernetes keep API keys secret?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "llnate keys encrypts your credentials with sops and age into a keys.env file that is safe to commit — it is ciphertext. The matching private key lives only in the cloud, guarded and encrypted at rest. At startup your agent decrypts credentials in memory via sops exec-env, so plaintext never touches disk. Your credentials are readable by exactly one thing: your running agent."
            }
          },
          {
            "@type": "Question",
            "name": "How do I get access to Layernetes?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "Layernetes is members-only for now. Become a member at frontiertower.io, join the AI floor, then email business@sanscourier.ai for access. The platform source is open (AGPL-3.0-or-later), so you can also self-host it on any Kubernetes cluster."
            }
          },
          {
            "@type": "Question",
            "name": "Is Layernetes open source?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "Yes — the full platform (CLI, control plane, operator, base image, Helm charts) is published under AGPL-3.0-or-later at github.com/elg0nz/layernetes. Sanscourier.ai licenses it to Learning Layer for the hosted cloud and offers commercial terms via business@sanscourier.ai."
            }
          }
        ]
      }
---

Layernetes turns a local AI agent into a live, public URL with one command. Write your agent, run `llnate push`, and it deploys with its own address, callable over MCP or plain HTTP.

It's built by [Sanscourier.ai](https://sanscourier.ai) and runs as the private cloud for [Learning Layer](https://www.learninglayer.ai/)'s AI floor. It's open source under the [AGPL](https://github.com/elg0nz/layernetes).

New here? Read [Introducing Layernetes](/blog/introducing-layernetes/) for the guided tour. This page is the quick reference.

## Quickstart

```sh
llnate init my-agent      # scaffold your agent plus everything the cloud expects
cd my-agent
llnate plugin install     # bring your AI coding assistant into the loop
# ... build your agent, the way you build everything now ...
llnate login              # provisions your cloud repo and encryption keys
llnate keys               # encrypt your API keys into the repo
llnate push               # deploy, streams progress, prints your URLs
```

`llnate push` blocks until your agent is live, then prints its public URLs. Anyone can call it:

- **MCP.** Every agent ships a built-in [FastMCP](https://github.com/jlowin/fastmcp) server, so it plugs into MCP clients like Claude.
- **HTTP.** A plain [FastAPI](https://fastapi.tiangolo.com/) interface for everything else.

## Secrets: `llnate keys`

Your agent needs credentials, and they never sit in a repo in plaintext. Layernetes encrypts them with [sops](https://github.com/getsops/sops) and [age](https://github.com/FiloSottile/age):

1. `llnate login` issues you an age public key.
2. `llnate keys` encrypts your credentials with it into a `keys.env` file you commit alongside your code. It's ciphertext, safe in git.
3. The matching private key lives only in the cloud, guarded and encrypted at rest.
4. At deploy time your agent decrypts them in memory at startup. Plaintext never touches disk.

Your credentials are readable by exactly one thing: your running agent.

## How it works

1. **Login.** `llnate login` provisions your repo and age keypair, and points your git remote at the cloud.
2. **Push.** `llnate push` pushes your code. A pipeline builds your agent into an image.
3. **Deploy.** The platform brings your agent up in its own isolated space, with your encrypted keys mounted in.
4. **Expose.** Your agent gets a public address that includes the fingerprint of the deployed code, so every revision has a stable URL.
5. **Serve.** Clients reach it over MCP or HTTP.

Each agent runs isolated, on the Learning Layer cloud's own hardware. The full architecture, the security model, and the local development guide live in the [repo](https://github.com/elg0nz/layernetes).

## Packages

| Package | What it is |
| --- | --- |
| `llnate` | The CLI: `init`, `plugin install`, `login`, `keys`, `push` |
| `ll-api` | Control-plane API: login, repo provisioning, key issuance, deploy status |
| `ll-operator` | Brings each agent up as a running deployment |
| `llagent-base` | The base image every agent builds on: the runtime, the MCP and HTTP wrapper, sops and age |
| `ll-infra` | Charts for the platform itself |

## Get access

Layernetes is members only for now. To try it:

1. Become a member at [Frontier Tower](https://frontiertower.io) and join the AI floor.
2. Email [business@sanscourier.ai](mailto:business@sanscourier.ai) for access.

## FAQ

### What is Layernetes?

The Learning Layer cloud for AI agents, built by [Sanscourier.ai](https://sanscourier.ai). You write a CrewAI-powered agent locally, run `llnate push`, and it goes live at a public URL any human or any AI can call — over MCP or plain HTTP. The source is open under the AGPL at [github.com/elg0nz/layernetes](https://github.com/elg0nz/layernetes).

### How do I deploy an AI agent on Layernetes?

The six commands in the [Quickstart](#quickstart) above: `init`, `plugin install`, build, `login`, `keys`, `push`. `push` blocks until your agent is live, then prints its URLs. If you're an AI coding assistant setting this up, fetch [layernetes.wtp.io/setup](https://layernetes.wtp.io/setup) for step-by-step instructions written for you.

### How do I call a deployed agent from Claude or another MCP client?

Every deployed agent serves a FastMCP endpoint at `/mcp` on its public URL:

```sh
claude mcp add --transport http my-agent https://<sha>.agents.wtp.io/mcp
```

The same address also answers plain HTTP — `POST /kickoff` runs the agent, `/docs` is the interactive API reference, `GET /healthz` reports liveness.

### How are my API keys kept secret?

`llnate keys` encrypts them with sops and age into a committed `keys.env` — ciphertext, safe in git. Your agent decrypts them in memory at startup; plaintext never touches disk. See [Secrets](#secrets-llnate-keys) above.

### How do I get access?

It's members-only for now — see [Get access](#get-access) above. The platform is open source, so you can also self-host it on any Kubernetes cluster.
