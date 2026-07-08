---
title: Overview
description: What Layernetes is, how to ship an agent, and how it works, in one page.
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
