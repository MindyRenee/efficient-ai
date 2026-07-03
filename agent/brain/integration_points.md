---
name: Integration Points
---

# Integration Points

Systems our AI company connects to.

## Inference Backend

### Efficient AI Proxy

- **Purpose**: All agent inference (decisions, content generation, lead scoring)
- **Endpoint**: http://localhost:8000/v1/chat/completions
- **Authentication**: None (local)
- **Routing**: Engine → Ollama → Cloud (automatic)
- **Cost tracking**: Built-in via _efficient metadata

## Content Platforms

### Medium / Dev.to

- **Purpose**: Publish technical blog posts
- **Status**: Manual (agent generates drafts, human publishes)

### Reddit

- **Purpose**: Build reputation, find gig opportunities
- **Subreddits**: r/LocalLLaMA, r/MachineLearning, r/ollama
- **Status**: Manual (agent drafts comments, human posts)

## Freelance Platforms

### Upwork

- **Purpose**: Find AI/ML consulting gigs
- **Status**: Manual (agent suggests opportunities, human applies)

### Hacker News

- **Purpose**: Show HN posts, find gig leads
- **Status**: Manual (agent identifies timing opportunities)

## Configuration

### Environment Variables

- EFFICIENT_HOST: Efficient AI server URL (default: http://localhost:8000)
- NODE_ENV: production/development
