# Branch Protection Setup Instructions

## Overview
This repository uses branch protection to ensure all changes go through pull requests before being merged to main.

## GitHub Repository Setup

### 1. Add GitHub Secrets
First, set up the required secrets for CI/CD:

1. Go to your GitHub repository
2. Click **Settings** tab
3. Click **Secrets and variables** → **Actions**
4. Add these repository secrets:
   - `ANTHROPIC_API_KEY` - Your Anthropic API key for testing
   - `RAILWAY_TOKEN_STAGING` - Railway token for staging deployment

### 2. GitHub Branch Protection Settings

#### 2.1. Go to Repository Settings
1. Navigate to your GitHub repository
2. Click **Settings** tab
3. Click **Branches** in the left sidebar

#### 2.2. Add Branch Protection Rule
1. Click **Add rule**
2. Branch name pattern: `main`

#### 2.3. Configure Protection Settings
Enable these settings:

#### Required Status Checks
- ✅ **Require status checks to pass before merging**
- ✅ **Require branches to be up to date before merging**
- Select status checks:
  - `lint` (from GitHub Actions)

#### Pull Request Requirements
- ✅ **Require a pull request before merging**
- ✅ **Require approvals**: Set to `1` (or more if you have a team)
- ✅ **Dismiss stale reviews when new commits are pushed**
- ✅ **Require review from code owners** (optional)

#### Additional Restrictions
- ✅ **Restrict pushes that create files that match a gitignored pattern**
- ✅ **Do not allow bypassing the above settings**
- ❌ **Allow force pushes** (keep disabled)
- ❌ **Allow deletions** (keep disabled)

#### Admin Enforcement
- ✅ **Include administrators** (recommended for consistency)

#### 2.4. Save Protection Rule
Click **Create** to save the branch protection rule.

## 3. Workflow After Setup

### For Contributors:
1. **Create feature branch**: `git checkout -b feature/your-feature`
2. **Make changes**: Commit your changes to the feature branch
3. **Push branch**: `git push origin feature/your-feature`
4. **Create PR**: Go to GitHub and create a pull request to `main`
5. **Wait for CI**: GitHub Actions will run tests automatically
6. **Request review**: Ask for code review if required
7. **Merge**: Once approved and tests pass, merge the PR

### For Deployments:
- **Pull Requests**: Deploy to staging for testing
- **Main Branch**: After PR merge, automatically deploys to production
- **Production**: Removed from pipeline (manual deployment when ready)

## Current CI/CD Flow:
```
Feature Branch → Pull Request → Tests Run → Review → Merge to Main → Deploy to Staging
```

This ensures:
- All code is tested before merging
- All changes are reviewed
- Only stable code reaches main branch
- Automatic staging deployment after merge
