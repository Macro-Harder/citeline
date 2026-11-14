# Citeline

Citeline audits a web page and a set of sampled AI
answers for citability signals: whether the page
carries the signals that make it likely to be named
or cited when an AI system answers a question about
the product the page describes.

It measures presence only. A Citeline score is a
signal index. It is not validated as a predictor of
citation, and it does not verify the truth of
anything the page or an answer says.

## What it does

- Registers the products, competitors, aliases,
  category terms, and query sets you state, in a
  local journal that every later act reads back.
- Audits one supplied page file against a set of
  weighted checks and stores the resulting audit
  record, with the evidence each check found.
- Evaluates a supplied robots file, standalone or
  beside an audit, and can preview how a second
  robots file changes the first one's answers.
- Imports sampled answers you supply as files,
  labels each one, and measures how often the
  product is named, named early, and cited, per
  query, per competitor, and per alias, with rates,
  intervals, and freshness over a 90 day full
  credit band shared by all product types.
- Reports any stored record in three forms:
  Simple (plain prose), Advanced (the record with
  its bounds stated beside its figures), and
  Agentic (the same payload for another program to
  consume). Reporting adds no number to what is
  stored.
- Drafts a guide from a completed audit record or
  round: the canonical line, an evidence sentence
  where the record supports one, and an ordered
  list of work.
- Runs scheduled watch rounds from a plan file you
  supply, covering either the targets the plan
  picks or the whole estate, as the plan states.

Third party mentions stand outside version 1
measurement, and no figure speaks for them.

## Boundaries

Citeline works on files only. It never fetches a
page, never captures an answer, and never follows
a link. Every input is a file you supply locally:
a page file, a robots file, an answer file, a
watch plan. Dates are inputs to each call, never
read from a clock. Truth verification is deferred
to a later version.

## Requirements

Python 3.11 or later. Standard library only; there
is nothing else to install.

## Install

Run the installer module from this repository,
stating where the package is placed and where its
home is:

    python install.py --location <dir> --home <dir>

The installer records what it created. The
matching uninstall removes only what the installer
created:

    python install.py --uninstall --location <dir> --home <dir>

## Use

The invocation surface is the citeline shell, one
subcommand per call, every input a named flag:

    add-product --home --name --canonical_line --domain --competitors --aliases --query_set --audit_date
    set-canonical-line --home --product --line --audit_date
    set-competitors --home --product --competitors --audit_date
    set-aliases --home --product --aliases --audit_date
    set-query-set --home --product --query_set --audit_date
    set-category --home --product --category_terms --audit_date
    register-page --home --product --snapshot --audit_date
    name-round --home --product --round_label --importer_declaration --supplier_relation --audit_date
    audit --home --page_file --robots_file --evaluated_page_path --audit_date
    robots --home --robots_file --evaluated_page_path --form --audit_date
    robots-preview --home --first_robots_file --second_robots_file --evaluated_page_path --first_capture_date --second_capture_date --form --audit_date
    probe import --home --answer_file --product --round --engine_label --query --kind --captured_on --capture_method --control_designation --audit_date
    probe report --home --product --round --form --audit_date
    probe trend --home --product --round_a --round_b --form --audit_date
    query-set-report --home --product --form --audit_date
    guide --home --run_id --product --round_label --audit_date
    verify --home
    status --home --form
    watch --plan
    help

Forms are simple, advanced, and agentic.

## Tests

The test suite stands in tests/ and runs against
the package in this repository:

    PYTHONPATH=. python3 -m unittest discover -s tests

## License

Apache License 2.0. See LICENSE. Copyright
J.P. Picard aka Macro-Harder.
