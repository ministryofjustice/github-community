import csv
import io
import unittest
from datetime import date, datetime

from app.projects.repository_stats.services.visibility_logic import (
    ActivityItem,
    ArchivedRepository,
    DateRangeResult,
    SnapshotCounts,
    TransitionCount,
    VisibilityEvent,
    VisibilityFilters,
    VisibilityQuery,
    VisibilitySnapshot,
    activity_csv,
    activity_csv_filename,
    archived_heading,
    archived_progress,
    archived_public_repositories,
    build_activity_items,
    changes_heading,
    count_changes,
    count_event_type,
    count_snapshot,
    count_transitions,
    csv_safe,
    filter_activity,
    filter_events_in_range,
    page_numbers,
    paginate,
    parse_archived_query,
    parse_only_public,
    parse_visibility_query,
    sort_activity,
    sort_archived,
    summary_heading,
    validate_date_range,
)

ORG = "ministryofjustice"
AUG_1 = date(2026, 8, 1)
SEP_25 = date(2026, 9, 25)


def snapshot(
    github_id, name, visibility, captured_on=SEP_25, archived=False, fork=False, org=ORG
):
    return VisibilitySnapshot(
        github_id=github_id,
        org=org,
        name=name,
        visibility=visibility,
        archived=archived,
        captured_on=captured_on,
        fork=fork,
    )


def event(
    github_id,
    name,
    event_type,
    from_v=None,
    to_v=None,
    occurred_on=date(2026, 8, 10),
    actor=None,
):
    return VisibilityEvent(
        github_id=github_id,
        org=ORG,
        name=name,
        event_type=event_type,
        occurred_on=occurred_on,
        source="scan",
        from_visibility=from_v,
        to_visibility=to_v,
        actor=actor,
    )


def item(
    name,
    kind="changed",
    from_v="public",
    to_v="internal",
    day=date(2026, 8, 10),
    bus=(),
    actor=None,
    org=ORG,
):
    return ActivityItem(
        github_id=hash(name) % 1000,
        name=name,
        org=org,
        business_units=tuple(bus),
        kind=kind,
        occurred_on=day,
        from_visibility=from_v,
        to_visibility=to_v,
        actor=actor,
    )


class TestValidateDateRange(unittest.TestCase):
    def test_uses_defaults_when_blank(self):
        result = validate_date_range(None, "", AUG_1, SEP_25)
        self.assertTrue(result.is_valid)
        self.assertEqual((result.from_date, result.to_date), (AUG_1, SEP_25))
        self.assertEqual(result.from_value, "2026-08-01")

    def test_accepts_valid_and_same_day_ranges(self):
        self.assertTrue(
            validate_date_range("2026-08-10", "2026-08-20", AUG_1, SEP_25).is_valid
        )
        self.assertTrue(
            validate_date_range("2026-08-10", "2026-08-10", AUG_1, SEP_25).is_valid
        )

    def test_rejects_from_after_to(self):
        result = validate_date_range("2026-09-30", "2026-08-01", AUG_1, SEP_25)
        self.assertFalse(result.is_valid)
        self.assertIn("from", result.errors)
        self.assertNotIn("to", result.errors)

    def test_records_what_the_user_entered(self):
        self.assertEqual(
            [
                (r.from_entered, r.to_entered)
                for r in (
                    validate_date_range("", " ", AUG_1, SEP_25),
                    validate_date_range("2026-08-10", "", AUG_1, SEP_25),
                    validate_date_range("", "2026-08-10", AUG_1, SEP_25),
                    validate_date_range("2026-08-10", "2026-08-11", AUG_1, SEP_25),
                )
            ],
            [(False, False), (True, False), (False, True), (True, True)],
        )

    def test_from_before_earliest_is_clamped_keeping_the_entered_value(self):
        result = validate_date_range(
            "2026-07-01", "2026-08-10", AUG_1, SEP_25, earliest=AUG_1
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.from_date, AUG_1)
        self.assertEqual(result.from_value, "2026-07-01")
        self.assertTrue(result.from_entered)

    def test_no_clamp_when_from_is_after_earliest_or_to_is_before_it(self):
        self.assertEqual(
            validate_date_range(
                "2026-08-10", "", AUG_1, SEP_25, earliest=AUG_1
            ).from_date,
            date(2026, 8, 10),
        )
        before = validate_date_range(
            "2026-07-01", "2026-07-05", AUG_1, SEP_25, earliest=AUG_1
        )
        self.assertTrue(before.is_valid)
        self.assertEqual(before.from_date, date(2026, 7, 1))

    def test_today_is_allowed_but_the_future_is_not(self):
        today = date(2026, 10, 1)
        self.assertTrue(
            validate_date_range(
                "2026-10-01", "2026-10-01", AUG_1, today, today
            ).is_valid
        )
        result = validate_date_range("2026-10-02", "", AUG_1, today, today)
        self.assertEqual(
            result.errors, {"from": "The 'from' date must be today or in the past"}
        )
        result = validate_date_range("", "2026-10-02", AUG_1, SEP_25, today)
        self.assertEqual(
            result.errors, {"to": "The 'to' date must be today or in the past"}
        )
        result = validate_date_range("2026-10-05", "2026-10-02", AUG_1, SEP_25, today)
        self.assertEqual(
            result.errors,
            {
                "from": "The 'from' date must be today or in the past",
                "to": "The 'to' date must be today or in the past",
            },
        )

    def test_from_after_to_message(self):
        result = validate_date_range("2026-09-02", "2026-09-01", AUG_1, SEP_25, SEP_25)
        self.assertEqual(
            result.errors,
            {"from": "The 'from' date must be the same as or before the 'to' date"},
        )

    def test_to_before_the_default_from_moves_from_back_without_error(self):
        result = validate_date_range("", "2026-07-15", AUG_1, SEP_25, SEP_25)
        self.assertTrue(result.is_valid)
        self.assertEqual(
            (result.from_date, result.to_date), (date(2026, 7, 15), date(2026, 7, 15))
        )

    def test_rejects_invalid_dates(self):
        result = validate_date_range("not-a-date", "2026-02-30", AUG_1, SEP_25)
        self.assertEqual(set(result.errors), {"from", "to"})
        self.assertIsNone(result.from_date)


class TestQueryParsing(unittest.TestCase):
    def test_defaults(self):
        query = parse_visibility_query({})
        self.assertEqual(query, VisibilityQuery())
        self.assertEqual(query.to_params(), {})
        self.assertEqual(query.query_string(), "")

    def test_invalid_values_fall_back_to_defaults(self):
        query = parse_visibility_query(
            {
                "sort": "bogus",
                "dir": "sideways",
                "activity": "x",
                "tab": "archived",
                "page": "abc",
            }
        )
        self.assertEqual(
            (query.sort, query.direction, query.activity, query.page),
            ("date", "desc", "all", 1),
        )
        self.assertFalse(hasattr(query, "tab"))
        self.assertNotIn("tab", query.to_params())
        self.assertEqual(parse_visibility_query({"page": "-3"}).page, 1)

    def test_non_date_sort_defaults_to_ascending(self):
        self.assertEqual(
            parse_visibility_query({"sort": "repository"}).direction, "asc"
        )

    def test_only_public_checkbox(self):
        self.assertTrue(parse_only_public([]))
        self.assertTrue(parse_only_public(["0", "1"]))
        self.assertFalse(parse_only_public(["0"]))

    def test_round_trip_params(self):
        args = {
            "org": ORG,
            "business_unit": "HMPPS",
            "q": "case",
            "from": "2026-08-01",
            "to": "2026-09-01",
            "activity": "new",
            "sort": "repository",
            "dir": "desc",
            "page": "2",
        }
        query = parse_visibility_query(args, ["0"])
        self.assertEqual(query.to_params(), {**args, "only_public": "0"})
        self.assertEqual(parse_visibility_query(query.to_params(), ["0"]), query)

    def test_sort_links_toggle_and_reset_page(self):
        query = parse_visibility_query({"page": "3"})
        self.assertEqual(query.sort_query_string("date"), "?sort=date&dir=asc")
        self.assertEqual(
            query.sort_query_string("repository"), "?sort=repository&dir=asc"
        )
        self.assertEqual(query.aria_sort("date"), "descending")
        self.assertEqual(query.aria_sort("by"), "none")
        ascending = parse_visibility_query({"sort": "repository", "dir": "asc"})
        self.assertEqual(
            ascending.sort_query_string("repository"), "?sort=repository&dir=desc"
        )
        self.assertEqual(ascending.aria_sort("repository"), "ascending")


class TestFilters(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(VisibilityFilters().matches(ORG, "anything", ()))
        self.assertTrue(VisibilityFilters(q="CASE").matches(ORG, "sample-case-api", ()))
        self.assertFalse(
            VisibilityFilters(q="court").matches(ORG, "sample-case-api", ())
        )
        self.assertFalse(VisibilityFilters(org="other").matches(ORG, "x", ()))
        self.assertTrue(
            VisibilityFilters(business_unit="LAA").matches(ORG, "x", ["HMPPS", "LAA"])
        )
        self.assertFalse(VisibilityFilters(business_unit="LAA").matches(ORG, "x", []))


class TestCounts(unittest.TestCase):
    def test_count_snapshot(self):
        snapshots = [
            snapshot(1, "a", "public"),
            snapshot(2, "b", "public", fork=True),
            snapshot(3, "c", "internal"),
            snapshot(4, "d", "private", archived=True),
        ]
        self.assertEqual(count_snapshot(snapshots), SnapshotCounts(4, 2, 1, 1))
        self.assertEqual(count_snapshot([]), SnapshotCounts())

    def test_transitions_include_all_six_in_fixed_order(self):
        events = [
            event(1, "a", "changed", "public", "private"),
            event(2, "b", "changed", "public", "private"),
            event(3, "c", "changed", "private", "public"),
            event(4, "d", "created", None, "public"),
            event(5, "e", "deleted", "private", None),
            event(6, "f", "archived"),
            event(7, "g", "changed", "public", None),
        ]
        transitions = count_transitions(events)
        self.assertEqual(len(transitions), 6)
        self.assertEqual(transitions[0], TransitionCount("public", "internal", 0))
        self.assertEqual(transitions[1], TransitionCount("public", "private", 2))
        self.assertEqual(transitions[4], TransitionCount("private", "public", 1))
        self.assertEqual(count_changes(events), 4)
        self.assertEqual(count_event_type(events, "created"), 1)

    def test_filter_events_in_range_is_inclusive(self):
        events = [
            event(1, "a", "changed", "public", "private", date(2026, 8, 1)),
            event(2, "b", "changed", "public", "private", date(2026, 8, 15)),
            event(3, "c", "changed", "public", "private", date(2026, 9, 1)),
        ]
        result = filter_events_in_range(events, date(2026, 8, 1), date(2026, 8, 15))
        self.assertEqual([e.name for e in result], ["a", "b"])


class TestActivity(unittest.TestCase):
    def setUp(self):
        self.events = [
            event(1, "sample-a", "changed", "public", "internal", date(2026, 8, 3)),
            event(
                2,
                "sample-b",
                "created",
                None,
                "public",
                date(2026, 8, 5),
                actor="octocat",
            ),
            event(3, "sample-c", "changed", "private", "public", date(2026, 8, 20)),
            event(3, "sample-c", "deleted", "public", None, date(2026, 9, 1)),
            event(4, "sample-d", "archived", None, None, date(2026, 9, 2)),
        ]
        self.items = build_activity_items(self.events, {"sample-a": ["HMPPS", "LAA"]})

    def test_build_items_labels_and_deleted_flag(self):
        self.assertEqual(
            [i.label for i in self.items],
            [
                "Public to internal",
                "New, created as public",
                "Private to public",
                "Deleted, was public",
            ],
        )
        self.assertEqual(self.items[0].business_unit_text, "HMPPS, LAA")
        self.assertEqual(self.items[1].business_unit_text, "None")
        self.assertEqual(self.items[0].by, "Not known")
        self.assertEqual(self.items[1].by, "octocat")
        self.assertEqual(
            [i.repository_deleted for i in self.items], [False, False, True, True]
        )
        self.assertEqual(
            self.items[0].github_url, "https://github.com/ministryofjustice/sample-a"
        )

    def test_filter_activity(self):
        self.assertEqual(len(filter_activity(self.items, "all")), 4)
        self.assertEqual(len(filter_activity(self.items, "changes")), 2)
        self.assertEqual(
            [i.name for i in filter_activity(self.items, "private-to-public")],
            ["sample-c"],
        )
        self.assertEqual(
            [i.name for i in filter_activity(self.items, "new")], ["sample-b"]
        )
        self.assertEqual(
            [i.kind for i in filter_activity(self.items, "deleted")], ["deleted"]
        )
        self.assertEqual(filter_activity(self.items, "internal-to-private"), [])

    def test_default_sort_is_newest_first(self):
        self.assertEqual(
            [i.occurred_on for i in sort_activity(self.items)],
            [date(2026, 9, 1), date(2026, 8, 20), date(2026, 8, 5), date(2026, 8, 3)],
        )

    def test_sort_by_column_with_ties_newest_first(self):
        items = [
            item("b", day=date(2026, 8, 1)),
            item("a", day=date(2026, 8, 1)),
            item("a", day=date(2026, 8, 9)),
            item("C", day=date(2026, 8, 5)),
        ]
        result = sort_activity(items, "repository", "asc")
        self.assertEqual(
            [(i.name, i.occurred_on.day) for i in result],
            [("a", 9), ("a", 1), ("b", 1), ("C", 5)],
        )
        self.assertEqual(sort_activity(items, "repository", "desc")[0].name, "C")
        by_bu = sort_activity(
            [item("x", bus=["OPG"]), item("y", bus=["CICA"]), item("z")],
            "business_unit",
            "asc",
        )
        self.assertEqual([i.name for i in by_bu], ["y", "z", "x"])

    def test_organisation_sorts_by_the_name_shown(self):
        items = [
            item("x", org="aaa-login"),
            item("y", org="zzz-login"),
            item("z", org="mmm"),
        ]
        names = {"aaa-login": "Zeta Organisation", "zzz-login": "Alpha Organisation"}
        self.assertEqual(
            [i.name for i in sort_activity(items, "organisation", "asc", names)],
            ["y", "z", "x"],
        )
        self.assertEqual(
            [i.name for i in sort_activity(items, "organisation", "asc")],
            ["x", "z", "y"],
        )


class TestPagination(unittest.TestCase):
    def test_pages_and_bounds(self):
        items = list(range(60))
        page = paginate(items, 2, 25)
        self.assertEqual(page.items, list(range(25, 50)))
        self.assertEqual(
            (page.first_item_number, page.last_item_number, page.total_pages),
            (26, 50, 3),
        )
        last = paginate(items, 3, 25)
        self.assertEqual((last.first_item_number, last.last_item_number), (51, 60))

    def test_clamps_out_of_range(self):
        self.assertEqual(paginate(list(range(30)), 99, 25).page, 2)
        self.assertEqual(paginate(list(range(30)), 0, 25).page, 1)
        empty = paginate([], 5, 25)
        self.assertEqual(
            (
                empty.page,
                empty.total_pages,
                empty.first_item_number,
                empty.last_item_number,
            ),
            (1, 1, 0, 0),
        )

    def test_rejects_bad_page_size(self):
        with self.assertRaises(ValueError):
            paginate([1], 1, 0)

    def test_page_numbers_with_ellipsis(self):
        self.assertEqual(
            page_numbers(paginate(list(range(250)), 6, 25)),
            [1, None, 4, 5, 6, 7, 8, None, 10],
        )
        self.assertEqual(page_numbers(paginate(list(range(50)), 1, 25)), [1, 2])


class TestArchived(unittest.TestCase):
    def test_scope_progress_and_sorting(self):
        aug = [
            snapshot(1, "old-public", "public", AUG_1, archived=True),
            snapshot(2, "old-moved", "public", AUG_1, archived=True, fork=True),
            snapshot(3, "old-internal", "internal", AUG_1, archived=True),
            snapshot(4, "archived-later", "public", AUG_1),
            snapshot(5, "active", "public", AUG_1),
            snapshot(6, "old-deleted", "public", AUG_1, archived=True),
            snapshot(7, "private-archived-later", "private", AUG_1),
        ]
        sep = [
            snapshot(1, "old-public", "public", archived=True),
            snapshot(2, "old-moved", "internal", archived=True, fork=True),
            snapshot(3, "old-internal", "internal", archived=True),
            snapshot(4, "archived-later", "public", archived=True),
            snapshot(5, "active", "public"),
            snapshot(7, "private-archived-later", "private", archived=True),
        ]
        events = [
            event(2, "old-moved", "changed", "public", "internal", date(2026, 8, 20)),
            event(4, "archived-later", "archived", occurred_on=date(2026, 9, 3)),
            event(6, "old-deleted", "deleted", "public", None, date(2026, 9, 5)),
            event(
                7, "private-archived-later", "archived", occurred_on=date(2026, 9, 4)
            ),
        ]
        repositories = archived_public_repositories(
            aug,
            AUG_1,
            events,
            sep,
            {1: AUG_1, 2: AUG_1, 3: AUG_1, 7: SEP_25},
            {"old-public": ["HMPPS"]},
        )
        self.assertEqual(
            {r.name for r in repositories},
            {"old-public", "old-moved", "archived-later"},
        )
        progress = archived_progress(repositories)
        self.assertEqual(
            (progress.total, progress.made_internal, progress.percent), (3, 1, 33)
        )
        ordered = sort_archived(repositories)
        self.assertEqual(
            [r.name for r in ordered], ["old-public", "archived-later", "old-moved"]
        )
        by_name = {r.name: r for r in repositories}
        self.assertEqual(by_name["archived-later"].first_archived_on, date(2026, 9, 3))
        self.assertEqual(by_name["old-public"].business_unit_text, "HMPPS")
        self.assertTrue(by_name["old-moved"].fork)

    def test_progress_percent(self):
        def repo(visibility):
            return ArchivedRepository(1, "r", ORG, (), visibility, AUG_1, None)

        self.assertEqual(archived_progress([]).percent, 0)
        self.assertEqual(
            archived_progress([repo("internal"), repo("public")]).percent, 50
        )
        self.assertEqual(
            archived_progress(
                [repo("private"), repo("internal"), repo("public")]
            ).percent,
            67,
        )


class TestCsv(unittest.TestCase):
    def test_csv_safe(self):
        for value in ("=SUM(A1)", "+1", "-1", "@cmd", "\tx", "\rx"):
            self.assertEqual(csv_safe(value), "'" + value)
        self.assertEqual(csv_safe("sample-case-api"), "sample-case-api")
        self.assertEqual(csv_safe(""), "")

    def test_activity_csv(self):
        items = [
            item('=HYPERLINK("x")', bus=["HMPPS", "LAA"], day=date(2026, 8, 2)),
            item(
                "sample-b", kind="created", from_v=None, to_v="public", actor="@octocat"
            ),
        ]
        rows = list(csv.reader(io.StringIO(activity_csv(items))))
        self.assertEqual(
            rows[0],
            ["repository", "organisation", "business_unit", "activity", "date", "by"],
        )
        self.assertEqual(
            rows[1],
            [
                '\'=HYPERLINK("x")',
                ORG,
                "HMPPS, LAA",
                "Public to internal",
                "2026-08-02",
                "Not known",
            ],
        )
        self.assertEqual(
            rows[2][3:], ["New, created as public", "2026-08-10", "'@octocat"]
        )

    def test_filename(self):
        self.assertEqual(
            activity_csv_filename(AUG_1, SEP_25),
            "repository-activity-2026-08-01-to-2026-09-25.csv",
        )


class TestFormatting(unittest.TestCase):
    def test_pushed_at_datetime_supported_by_archived_rows(self):
        repository = ArchivedRepository(
            1,
            "r",
            ORG,
            (),
            "public",
            None,
            datetime(2024, 1, 2, 3, 4),  # noqa: DTZ001
        )
        self.assertTrue(repository.still_public)
        self.assertEqual(
            repository.github_url, "https://github.com/ministryofjustice/r"
        )


if __name__ == "__main__":
    unittest.main()


class TestSummaryHeading(unittest.TestCase):
    def test_same_year(self):
        self.assertEqual(
            summary_heading(AUG_1, SEP_25), "Summary, 1 August to 25 September 2026"
        )

    def test_cross_year(self):
        self.assertEqual(
            summary_heading(date(2025, 12, 3), date(2026, 1, 9)),
            "Summary, 3 December 2025 to 9 January 2026",
        )

    def test_missing_dates(self):
        self.assertEqual(summary_heading(None, SEP_25), "Summary")

    def test_single_day(self):
        self.assertEqual(summary_heading(SEP_25, SEP_25), "Summary, 25 September 2026")

    def test_changes_heading_single_day_for_every_entry(self):
        for from_entered, to_entered in ((True, False), (False, True), (True, True)):
            with self.subTest(from_entered=from_entered, to_entered=to_entered):
                result = DateRangeResult(
                    "", "", SEP_25, SEP_25, {}, from_entered, to_entered
                )
                self.assertEqual(
                    changes_heading(True, result), "Summary, 25 September 2026"
                )


class TestChangesHeading(unittest.TestCase):
    RANGE = DateRangeResult("", "", AUG_1, SEP_25)

    def test_no_heading_without_filters(self):
        self.assertIsNone(changes_heading(False, self.RANGE))

    def test_summary_worded_from_what_the_user_entered(self):
        def heading(from_entered, to_entered, from_date=AUG_1, to_date=SEP_25):
            return changes_heading(
                True,
                DateRangeResult(
                    "", "", from_date, to_date, {}, from_entered, to_entered
                ),
            )

        self.assertEqual(heading(False, False), "Summary, all dates")
        self.assertEqual(
            heading(True, False, date(2026, 9, 1), date(2026, 10, 1)),
            "Summary, 1 September to 1 October 2026",
        )
        self.assertEqual(heading(False, True), "Summary, 1 August to 25 September 2026")
        self.assertEqual(
            heading(True, True, date(2026, 9, 1), date(2026, 9, 15)),
            "Summary, 1 September to 15 September 2026",
        )
        self.assertEqual(
            heading(True, True, date(2025, 12, 3), date(2026, 1, 9)),
            "Summary, 3 December 2025 to 9 January 2026",
        )

    def test_invalid_range_is_plain_summary(self):
        invalid = DateRangeResult("x", "", None, SEP_25, {"from": "bad"}, True)
        self.assertEqual(changes_heading(True, invalid), "Summary")

    def test_filter_applied(self):
        self.assertFalse(VisibilityQuery().filter_applied)
        self.assertFalse(
            VisibilityQuery(
                activity="new", sort="repository", direction="asc", page=3
            ).filter_applied
        )
        for query in (
            VisibilityQuery(filters=VisibilityFilters(org="ministryofjustice")),
            VisibilityQuery(filters=VisibilityFilters(business_unit="HMPPS")),
            VisibilityQuery(filters=VisibilityFilters(q="api")),
            VisibilityQuery(from_value="2026-08-01"),
            VisibilityQuery(to_value="2026-09-25"),
        ):
            self.assertTrue(query.filter_applied)


class TestParseArchivedQuery(unittest.TestCase):
    def test_keeps_only_estate_filters_and_checkbox(self):
        query = parse_archived_query(
            {
                "org": ORG,
                "business_unit": "HMPPS",
                "q": " case ",
                "from": "2026-09-30",
                "to": "2026-08-01",
                "activity": "new",
                "sort": "repository",
                "page": "3",
            },
            ["0"],
        )
        self.assertEqual(
            query,
            VisibilityQuery(
                filters=VisibilityFilters(ORG, "HMPPS", "case"), only_public=False
            ),
        )
        self.assertEqual(
            query.to_params(),
            {"org": ORG, "business_unit": "HMPPS", "q": "case", "only_public": "0"},
        )
        self.assertTrue(query.filter_applied)
        self.assertTrue(query.estate_filter_applied)

    def test_defaults(self):
        self.assertEqual(parse_archived_query({}), VisibilityQuery())


class TestArchivedHeading(unittest.TestCase):
    def test_states(self):
        self.assertIsNone(archived_heading(False, SEP_25))
        self.assertIsNone(archived_heading(False, None))
        self.assertEqual(archived_heading(True, SEP_25), "Summary")
        self.assertIsNone(archived_heading(True, None))

    def test_dates_do_not_count_for_archived(self):
        self.assertFalse(
            VisibilityQuery(
                from_value="2026-08-01", to_value="2026-09-01"
            ).estate_filter_applied
        )
        self.assertTrue(VisibilityQuery(from_value="2026-08-01").filter_applied)
        for filters in (
            VisibilityFilters(org="o"),
            VisibilityFilters(business_unit="b"),
            VisibilityFilters(q="q"),
        ):
            self.assertTrue(VisibilityQuery(filters=filters).estate_filter_applied)
