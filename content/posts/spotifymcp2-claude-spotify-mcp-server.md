---
title: "SpotifyMCP2: Control Spotify with Claude via the Model Context Protocol"
date: 2026-02-24T11:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "tools", "ai"]
tags: ["MCP", "Claude", "Spotify", "TypeScript", "AI", "Model Context Protocol", "OAuth2", "API Integration", "Open Source", "Node.js"]
summary: "SpotifyMCP2 is a TypeScript MCP server that gives Claude direct control over Spotify — search tracks, manage playback, browse playlists, and queue songs through natural language. Built with full OAuth2, automatic token refresh, and 95%+ test coverage."
description: "A deep dive into SpotifyMCP2, an open-source Model Context Protocol server that integrates Claude with the Spotify Web API. Learn how it works, how to set it up, and how to extend it. Covers MCP architecture, OAuth2 flow, TypeScript design, and all 8 exposed tools."
readTime: "12 min"
---

## Introduction: Talking to Spotify Through Claude

Imagine typing to Claude: *"Play something calm and focused for deep work"* — and having Spotify actually respond. Not a suggestion, not a playlist link — Claude directly searching, selecting, and playing the right track.

**[SpotifyMCP2](https://github.com/yennanliu/SpotifyMCP2)** makes this possible. It's a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server written in TypeScript that exposes Spotify's playback, search, and playlist management capabilities as native Claude tools.

This is what AI-native music control looks like.

## What is the Model Context Protocol?

Before diving into SpotifyMCP2, a quick primer on MCP.

The **Model Context Protocol** is an open standard that allows AI assistants like Claude to communicate with external tools and services in a structured, typed way. Instead of relying on brittle prompt engineering or custom API wrappers, MCP defines a formal protocol where:

- **Tools** are defined with typed input schemas (JSON Schema)
- Claude can discover available tools and call them natively
- Results are returned in a structured format Claude can reason about

MCP servers can expose anything as a Claude tool: databases, file systems, APIs, IoT devices, or — as in this case — music streaming services.

## SpotifyMCP2: Feature Overview

SpotifyMCP2 exposes **8 MCP tools** covering the full Spotify control surface:

| Tool | Description |
|---|---|
| `search_tracks` | Search the Spotify catalog by query string |
| `play_track` | Play a specific track by URI or ID |
| `playback_control` | Play, pause, skip to next, or go to previous track |
| `get_current_playback` | Get the currently playing track and playback state |
| `get_user_playlists` | List the authenticated user's playlists |
| `get_playlist_tracks` | Retrieve all tracks from a specific playlist |
| `add_to_queue` | Add a track to the playback queue |
| `get_available_devices` | List all active Spotify devices |

Together, these tools give Claude the ability to act as a full-featured music assistant — without any plugins, browser extensions, or manual UI interaction.

## Technical Architecture

### Project Structure

```
SpotifyMCP2/
├── src/
│   ├── index.ts           # MCP server entry point and tool registration
│   ├── auth.ts            # OAuth2 authentication and token management
│   ├── spotify_api.ts     # Spotify Web API client with retry logic
│   ├── types.ts           # TypeScript type definitions
│   └── tools/
│       ├── search.ts      # search_tracks implementation
│       ├── playback.ts    # play_track, playback_control, get_current_playback
│       ├── playlist.ts    # get_user_playlists, get_playlist_tracks
│       └── device.ts      # get_available_devices, add_to_queue
├── tests/
│   ├── spotify_api.test.ts
│   └── mcp_tools.test.ts
├── ARCHITECTURE.md
├── SETUP.md
└── TEST_REPORT.md
```

### OAuth2 with Automatic Token Refresh

Spotify's API uses OAuth2, which means access tokens expire (typically after 1 hour). SpotifyMCP2 handles the full OAuth2 lifecycle in `auth.ts`:

1. **Initial Authorization**: Redirects to Spotify's authorization endpoint with required scopes
2. **Token Exchange**: Exchanges the authorization code for access + refresh tokens
3. **Automatic Refresh**: Before each API call, checks token expiry and silently refreshes using the stored refresh token
4. **Configuration via `.env`**: All credentials stored in environment variables

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
SPOTIFY_REFRESH_TOKEN=your_refresh_token
```

This means you authorize once during setup and never have to re-authenticate — the server handles it transparently.

### Resilient API Client with Exponential Backoff

The `spotify_api.ts` client wraps all Spotify API calls with production-grade error handling:

- **429 Rate Limiting**: Detects `Retry-After` headers and applies exponential backoff before retrying
- **503 Service Errors**: Temporary Spotify outages trigger automatic retries with jitter
- **Typed responses**: All API responses are typed via `types.ts` — no `any` in the codebase

### MCP Tool Registration

Each tool is registered in `index.ts` with a typed input schema:

```typescript
server.tool(
  "search_tracks",
  "Search for tracks on Spotify",
  {
    query: z.string().describe("Search query for tracks"),
    limit: z.number().optional().default(10).describe("Number of results to return"),
  },
  async ({ query, limit }) => {
    const results = await spotifyApi.searchTracks(query, limit);
    return {
      content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
    };
  }
);
```

Claude receives the tool definition, understands its purpose from the description and schema, and can call it autonomously during a conversation.

## Setup Guide

### Prerequisites

- Node.js 18+
- Spotify Premium account (required for playback control)
- A Spotify Developer App (free to create at [developer.spotify.com](https://developer.spotify.com))

### Step 1: Clone and Install

```bash
git clone https://github.com/yennanliu/SpotifyMCP2
cd SpotifyMCP2
npm install
```

### Step 2: Create a Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new application
3. Set Redirect URI to `http://localhost:8888/callback`
4. Copy your **Client ID** and **Client Secret**

### Step 3: Configure Environment

```bash
cp .env.example .env
```

Fill in your Spotify credentials:

```env
SPOTIFY_CLIENT_ID=abc123...
SPOTIFY_CLIENT_SECRET=xyz789...
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
SPOTIFY_REFRESH_TOKEN=  # filled in next step
```

### Step 4: Get Your Refresh Token

Run the auth helper script:

```bash
npm run get-token
```

Follow the browser OAuth flow. The script will print your `SPOTIFY_REFRESH_TOKEN` — paste it into `.env`.

### Step 5: Build

```bash
npm run build
```

### Step 6: Connect to Claude Desktop

Add SpotifyMCP2 to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "spotify": {
      "command": "node",
      "args": ["/path/to/SpotifyMCP2/dist/index.js"],
      "env": {
        "SPOTIFY_CLIENT_ID": "your_client_id",
        "SPOTIFY_CLIENT_SECRET": "your_client_secret",
        "SPOTIFY_REDIRECT_URI": "http://localhost:8888/callback",
        "SPOTIFY_REFRESH_TOKEN": "your_refresh_token"
      }
    }
  }
}
```

Restart Claude Desktop — you'll see the Spotify tools available in the tool picker.

## Real-World Usage Examples

Once connected, you can interact with Spotify through completely natural conversations:

**Music for focus:**
> *"I need to focus on some deep work. Search for lofi hip hop beats and play the first result."*

**Playlist exploration:**
> *"Show me my playlists and then play my 'Late Night Coding' playlist."*

**Playback control:**
> *"Skip this track, then tell me what's playing."*

**Queue management:**
> *"Find the song 'Midnight City' by M83 and add it to my queue."*

**Device management:**
> *"What devices do I have available? Switch playback to my MacBook."*

Claude handles the tool selection, sequencing, and error recovery automatically.

## Quality: 113 Tests, 95%+ Coverage

SpotifyMCP2 was built with testing as a first-class concern:

- **113 unit and integration tests** across `spotify_api.test.ts` and `mcp_tools.test.ts`
- **95%+ code coverage** — nearly every code path is tested
- Tests cover: OAuth token refresh, API error handling (429, 503), tool input validation, and MCP protocol conformance

```bash
npm test
# Runs all 113 tests
# Coverage report generated to ./coverage/
```

The `TEST_REPORT.md` and `ARCHITECTURE.md` in the repository provide detailed documentation of the design decisions and test strategies.

## Why MCP Over a Custom Plugin?

You might wonder: why use MCP instead of just a custom prompt + API integration?

| Approach | MCP | Custom Integration |
|---|---|---|
| Tool discovery | Automatic (Claude sees schema) | Manual prompt engineering |
| Type safety | JSON Schema enforced | None |
| Error handling | Structured responses | Free-form |
| Reusability | Any MCP-compatible client | Single-use |
| Maintenance | Protocol-versioned | Breaks with prompt changes |

MCP is the right abstraction: it separates the **what** (Spotify capabilities) from the **how** (Claude's reasoning), making both sides independently maintainable and upgradeable.

## What's Next

The repository currently has 8 open issues tracking planned enhancements:

- **Playlist creation and track management** (add/remove tracks from playlists)
- **Artist and album browsing** — not just track search
- **Recommendation engine integration** — use Spotify's recommendation API based on seed tracks
- **Liked songs / library management**
- **Multi-device transfer** — move playback between devices seamlessly

## Project Links

- **GitHub Repository**: [https://github.com/yennanliu/SpotifyMCP2](https://github.com/yennanliu/SpotifyMCP2)
- **Demo / Docs Site**: [https://yennj12.js.org/SpotifyMCP2/](https://yennj12.js.org/SpotifyMCP2/)

## Conclusion

SpotifyMCP2 demonstrates what's possible when you combine MCP's structured tool protocol with a well-designed API client. What was once a tedious combination of browser tabs, app switching, and manual track selection becomes a natural part of an AI-assisted workflow.

The architecture is clean, the test coverage is thorough, and the setup is straightforward. If you're building MCP servers or just want Claude to control your music, SpotifyMCP2 is a great starting point.

```bash
git clone https://github.com/yennanliu/SpotifyMCP2
npm install && npm run build
```

Give Claude the aux cord.
