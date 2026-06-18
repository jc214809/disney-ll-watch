# Disney Lightning Lane Watch

Static GitHub Pages dashboard plus GitHub Action updater for ThemeParks.wiki Lightning Lane Single Pass purchase availability.

## Setup

1. Upload these files to a GitHub repo.
2. Add repository secrets:
   - `PUSHOVER_APP_TOKEN`
   - `PUSHOVER_USER_KEY`
3. Enable GitHub Pages from the `main` branch and `/root` folder.
4. Go to Actions > Update Lightning Lane Data > Run workflow.

The workflow updates every 5 minutes. GitHub scheduled workflows can be delayed by GitHub, so it may not run exactly on the minute.

## Config

Edit `config.json` for trip dates and rides.

Alerts are sent when a watched ride changes from unavailable to available. The first run creates state and will not spam alerts for already-available rides.
