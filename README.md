# Citeline

Citeline audits a web page and a set of sampled AI
answers for citability signals: whether the page
carries the signals Citeline measures, and whether
the product is named and cited in the answers.

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
  Freshness is one of the page audit checks, over
  the 90 day full credit band shared by all product
  types.
- Evaluates a supplied robots file, standalone or
  beside an audit, and can preview how a second
  robots file changes the first one's answers.
- Imports sampled answers you supply as files,
  labels each one, and measures how often the
  product is named, named early, and cited, per
  query, per competitor, and per alias, with rates
  and intervals.
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
to a later version. Version 1 is English only.

## Requirements

Python 3.11 or later. Standard library only; there
is nothing else to install.

## Install

Run the installer file from this directory, with
one optional argument naming the install location:

    python install.py [location]

Where no argument stands, the install location is
the directory named citeline beside this directory.
The flag forms --location and --home stand accepted
beside the stated form, and --home names a product
home other than the default, a directory named
.citeline in your home directory. The install
output stands in the simple form only and states
the home path. The installer records what it
created. The matching uninstall, the word uninstall
as the first argument with the install location as
its optional second argument, removes only what
the installer created:

    python install.py uninstall [location]

## Use

The invocation surface is the citeline shell, one
subcommand per call, every input a named flag:

    add-product --home --name --canonical_line --domain --competitors --aliases --query_set --audit_date --form
    set-canonical-line --home --product --line --audit_date --form
    set-competitors --home --product --competitors --audit_date --form
    set-aliases --home --product --aliases --audit_date --form
    set-query-set --home --product --query_set --audit_date --form
    set-category --home --product --category_terms --audit_date --form
    register-page --home --product --snapshot --audit_date --form
    name-round --home --product --round_label --importer_declaration --supplier_relation --audit_date --form
    audit --home --page_file --robots_file --evaluated_page_path --audit_date --form
    robots --home --robots_file --evaluated_page_path --form --audit_date
    robots-preview --home --first_robots_file --second_robots_file --evaluated_page_path --first_capture_date --second_capture_date --form --audit_date
    probe import --home --answer_file --product --round --engine_label --query --kind --captured_on --capture_method --control_designation --audit_date --form
    probe report --home --product --round --form --audit_date
    probe trend --home --product --round_a --round_b --form --audit_date
    query-set-report --home --product --form --audit_date
    guide --home --run_id --product --round_label --audit_date --form
    verify --home --form
    status --home --form
    watch --plan --form
    help

Forms are simple, advanced, and agentic. The
subcommands above and watch each take --form. The
help line takes no flag. List valued inputs
(--competitors, --aliases, --query_set,
--category_terms) take a comma separated list, a
JSON list, or the flag repeated once per item.

--round and --round_label name the same input, the
round label. --captured_on is the date an answer
was captured; --audit_date is the date a call runs
as of, a different date from any capture date.

Values an operator supplies from closed sets:

- answer kind (--kind): real_sample, fixture
- control designation (--control_designation):
  positive, negative
- importer_declaration: all captured answers
  imported; a stated subset imported; selection
  rule unknown
- supplier_relation: supplied by the audited
  party; supplied by an independent party; supplier
  relation unknown
- watch scope: picked, estate

A watch plan file is a JSON object with keys home,
scope, targets, form, audit_date, output, and
cadence. Targets stands required where scope is
picked, each target naming a product and one of a
page file or a named round. A plan may also name a
second round per product for trend, under the key
second_round.

Score bands: strong at a score of 80 or more,
developing at 60 or more, thin at 40 or more, and
poor below 40, on a scale of 0 to 100, in that
order from highest to lowest.

The valid config keys and their defaults stand in
the shell help text, with one labelled fixture
example of a complete valid import.

## License

Apache License 2.0. See LICENSE. Copyright
J.P. Picard aka Macro-Harder.
