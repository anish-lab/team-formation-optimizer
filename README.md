# Team Formation (simple version)

Upload a CSV of people, answer a few questions, and get the teams. That is all the website does.

Teams are formed by the algorithms in San Segundo, Furini & Artieda, *"A new branch-and-bound algorithm for the Maximum Weighted Clique Problem"*, Computers & Operations Research 110 (2019) 18-33: AMTS for the first answer, then BBMCW.

## Run it

Backend, in one terminal:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Website, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. A sample file is in `backend/sample_data/students.csv`.

## Where the algorithm is

* `backend/optimization/bbmcw.py`: COLOR, COVER, MCOVER, GenBranchSet and the search
* `backend/optimization/amts.py`: AMTS
* `backend/optimization/team_conflict_solver.py`: turns the possible teams into the graph BBMCW solves
* `backend/optimization/split_solver.py`: big groups only (see below)

## Big groups

40 people in teams of 5 have 658,008 possible teams, too many for one search. So the site starts from any valid split of the people into teams, takes 2 to 4 teams at a time, re-solves just their members with AMTS and BBMCW, and keeps the new teams when they score higher.

This splitting is this project's own step, not from the paper. Every small search is the paper's algorithm, but the overall answer is the best found, not proven best, and the page says so.

## Limits

* The search stops after 20 seconds. The page says whether the teams are the best possible or only the best found in that time.
* Very large teams can still have too many possible teams, and the page says so. For example, 40 people in teams of 9 or 10 are refused, as are 40 people in teams of 7 when everyone must be in a team.

## Tests

```bash
cd backend
python -m pytest
```
