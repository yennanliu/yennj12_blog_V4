# YennJ12 Engineering Blog

A clean, minimal Hugo blog inspired by Uber's engineering blog design. Built with modern web technologies and optimized for technical content.

## Features

- 🎨 Clean, minimal design inspired by Uber's engineering blog
- 📱 Fully responsive mobile-first design
- 🔍 Built-in search functionality with live results
- 👥 Author profiles and bio pages
- 🏷️ Category and tag organization
- 📊 Reading progress indicator
- ⚡ Fast loading with optimized assets
- 🎯 SEO optimized with structured data
- ♿ Accessibility features (high contrast, reduced motion)

## Getting Started

### Prerequisites

- [Hugo Extended](https://gohugo.io/installation/) (v0.118.0 or later)
- Git

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd yennj12_blog_V4
```

2. Start the development server:
```bash
hugo server --buildDrafts
```

3. Open your browser and navigate to `http://localhost:1313`

## Writing New Blog Posts

### 1. Create a New Post

Use Hugo's archetype system to create a new post with the proper front matter:

```bash
hugo new content/posts/your-post-title.md
```

This will create a new file in `content/posts/` with the following template:

```yaml
---
title: "Your Post Title"
date: 2024-08-10T10:00:00Z
draft: true
authors: ["author-slug"]
categories: ["engineering", "architecture"]
tags: ["tag1", "tag2", "tag3"]
summary: "Brief description of your post for previews and SEO"
readTime: "10 min"
---

Your content goes here...
```

### 2. Configure Post Metadata

Fill in the front matter fields:

- **title**: Your post title
- **date**: Publication date in ISO 8601 format
- **draft**: Set to `false` when ready to publish
- **authors**: Array of author slugs (must match author directory names)
- **categories**: Main categories (engineering, architecture, data)
- **tags**: Specific technical tags
- **summary**: Brief description for cards and SEO
- **readTime**: Estimated reading time (e.g., "8 min")

### 3. Write Your Content

Write your post content in Markdown. The theme supports:

- Code syntax highlighting
- Tables and lists
- Blockquotes
- Images and media
- Math notation (KaTeX)

Example code block:
````markdown
```go
func main() {
    fmt.Println("Hello, World!")
}
```
````

### 4. Preview Your Post

Start the development server with drafts enabled:

```bash
hugo server --buildDrafts
```

Your draft post will be visible at `http://localhost:1313`

### 5. Publish Your Post

When ready to publish, set `draft: false` in the front matter:

```yaml
---
title: "Your Post Title"
draft: false
# ... other fields
---
```

## Adding New Authors

### 1. Create Author Directory

Create a new directory in `content/authors/` with the author's slug:

```bash
mkdir content/authors/jane-doe
```

### 2. Create Author Profile

Create `_index.md` in the author directory:

```yaml
---
title: "Jane Doe"
role: "Senior Software Engineer"
avatar: "/images/authors/jane-doe.jpg"
bio: "Jane is a senior software engineer specializing in distributed systems..."
social:
  twitter: "https://twitter.com/janedoe"
  linkedin: "https://linkedin.com/in/janedoe"
  github: "https://github.com/janedoe"
---

Extended bio content in Markdown format...
```

### 3. Add Author Avatar

Place the author's profile image in `static/images/authors/jane-doe.jpg`

## Running the App Locally

### Development Server

Start the Hugo development server:

```bash
# With draft posts visible
hugo server --buildDrafts

# Production-like build (drafts hidden)
hugo server

# Custom port
hugo server --port 1314

# Bind to all interfaces
hugo server --bind 0.0.0.0
```

The site will be available at `http://localhost:1313` with live reload enabled.

### Building for Production

Generate static files for deployment:

```bash
# Build optimized static site
hugo --minify

# Build with specific base URL
hugo --baseURL https://yourdomain.com --minify
```

Built files will be in the `public/` directory.

## Deployment

### Option 1: GitHub Pages

1. **Setup GitHub Actions** - Create `.github/workflows/hugo.yml`:

```yaml
name: Deploy Hugo site to Pages

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3
        
      - name: Setup Hugo
        uses: peaceiris/actions-hugo@v2
        with:
          hugo-version: 'latest'
          extended: true
          
      - name: Build
        run: hugo --minify
        
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v2
        with:
          path: ./public

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v2
```

2. **Configure Repository**:
   - Go to Settings → Pages
   - Source: GitHub Actions
   - Push to main branch to deploy

### Option 2: Netlify

1. **Connect Repository**:
   - Sign up at [netlify.com](https://netlify.com)
   - Connect your GitHub repository

2. **Build Settings**:
   - Build command: `hugo --minify`
   - Publish directory: `public`
   - Hugo version: Set in environment variable `HUGO_VERSION=0.121.1`

3. **Deploy**: Push to main branch for automatic deployment

### Option 3: Vercel

1. **Connect Repository**:
   - Sign up at [vercel.com](https://vercel.com)
   - Import your GitHub repository

2. **Framework Settings**:
   - Framework Preset: Hugo
   - Build command: `hugo --minify`
   - Output directory: `public`

3. **Environment Variables**:
   - `HUGO_VERSION`: `0.121.1`

### Option 4: Manual Deployment

1. **Build the site**:
```bash
hugo --minify --baseURL https://yourdomain.com
```

2. **Upload files**: Upload the `public/` directory contents to your web server

## Customization

### Theme Configuration

Edit `hugo.toml` to customize:

- Site title and description
- Navigation menu items
- Social media links
- SEO settings

### Styling

The theme uses SCSS with design tokens in `themes/uber-style/assets/scss/`:

- `_variables.scss` - Colors, typography, spacing
- `_mixins.scss` - Reusable style patterns
- `main.scss` - Main stylesheet

### Content Organization

```
content/
├── posts/           # Blog articles
├── authors/         # Author profiles  
├── categories/      # Category pages
├── tags/           # Tag pages
└── about/          # Static pages
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally with `hugo server`
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions or issues:
- Open a GitHub issue
- Check Hugo documentation at [gohugo.io](https://gohugo.io)
- Review theme documentation in `/themes/uber-style/README.md`
