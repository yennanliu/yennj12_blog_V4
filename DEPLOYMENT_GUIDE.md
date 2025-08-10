# GitHub Pages Deployment Guide

## 🚨 Fixing Deployment Errors

### Current Issue: Deprecated Action Version
GitHub has deprecated `actions/upload-artifact@v3`. The workflows have been updated to use the latest versions.

### Previous Issue: GitHub Pages Not Enabled
If you see "Pages not enabled" errors, GitHub Pages needs to be configured in repository settings.

### Step 1: Enable GitHub Pages

1. **Go to your GitHub repository**: https://github.com/yennanliu/yennj12_blog_V4
2. **Navigate to Settings** → **Pages** (in the left sidebar)
3. **Under "Source"**, select **"GitHub Actions"**
4. **Save the settings**

### Step 2: Choose Your Deployment Method

You now have **3 workflow options**:

1. **`hugo.yml`** - Main deployment workflow (updated with latest action versions)
2. **`hugo-latest.yml`** - Simplified workflow using peaceiris/actions-hugo (recommended)
3. **`deploy-alternative.yml`** - Backup workflow that just builds the site

**Recommended**: Use `hugo-latest.yml` for the most reliable deployment.

### Step 3: Re-run the Workflow

1. Go to the **Actions** tab in your repository
2. Find the failed workflow run (or manually trigger "Deploy Hugo to GitHub Pages (Latest)")
3. Click **"Re-run jobs"** → **"Re-run all jobs"**

## 📋 Complete Setup Checklist

### ✅ Repository Setup
- [ ] Repository is public (required for free GitHub Pages)
- [ ] Code is pushed to the `main` branch
- [ ] Workflow files are in `.github/workflows/`

### ✅ GitHub Pages Configuration
- [ ] Go to **Settings** → **Pages**
- [ ] Set **Source** to **"GitHub Actions"**
- [ ] Confirm settings are saved

### ✅ Workflow Permissions
The workflow should have these permissions (already configured):
- `contents: read`
- `pages: write` 
- `id-token: write`

## 🛠️ Alternative Deployment Methods

If GitHub Pages continues to have issues, here are alternatives:

### Option 1: Manual Build & Deploy
```bash
# Build the site locally
hugo --minify --baseURL https://yennanliu.github.io/yennj12_blog_V4/

# The public/ folder contains your static site
# Upload these files to any web host
```

### Option 2: Netlify (Recommended Alternative)
1. **Sign up**: https://netlify.com
2. **Connect GitHub repo**: Import your repository
3. **Build settings**:
   - Build command: `hugo --minify`
   - Publish directory: `public`
   - Environment variable: `HUGO_VERSION=0.121.1`

### Option 3: Vercel
1. **Sign up**: https://vercel.com
2. **Import repository** from GitHub
3. **Framework preset**: Hugo (auto-detected)
4. **Deploy**: Automatic on each push

## 🔍 Troubleshooting Common Issues

### Issue 1: "Pages not enabled" Error
**Solution**: Enable GitHub Pages in repository settings (see Step 1 above)

### Issue 2: 404 Error After Deployment
**Possible causes**:
- Base URL mismatch
- Repository name changed
- Files not in root of `public/` directory

**Solution**: Check that `baseURL` in `hugo.toml` matches your GitHub Pages URL

### Issue 3: Workflow Permission Denied
**Solution**: Ensure repository has proper workflow permissions:
1. **Settings** → **Actions** → **General**
2. **Workflow permissions**: Select "Read and write permissions"

### Issue 4: Hugo Version Mismatch
**Solution**: The workflow uses Hugo v0.121.1. If you need a different version:
1. Edit `.github/workflows/hugo.yml`
2. Change `HUGO_VERSION: 0.121.1` to your desired version

## 📊 Monitoring Deployment

### Check Build Status
1. **Actions tab**: View all workflow runs
2. **Green checkmark**: Successful deployment
3. **Red X**: Failed deployment (check logs)

### Access Your Site
Once deployed successfully, your site will be available at:
```
https://yennanliu.github.io/yennj12_blog_V4/
```

### Build Logs
If deployment fails:
1. Click on the failed workflow run
2. Click on the failed job (usually "build" or "deploy")
3. Review the error logs for specific issues

## 🎯 Quick Fix Commands

If you need to make quick fixes and redeploy:

```bash
# Make your changes, then:
git add .
git commit -m "Fix deployment issue"
git push origin main

# This will automatically trigger a new deployment
```

## 📞 Getting Help

If you're still having issues:
1. **Check the workflow logs** in the Actions tab
2. **Verify GitHub Pages settings** are correct
3. **Try the alternative workflow** in `.github/workflows/deploy-alternative.yml`
4. **Consider using Netlify or Vercel** as alternatives

The most common issue is simply forgetting to enable GitHub Pages in the repository settings. Once that's configured correctly, the deployment should work smoothly!