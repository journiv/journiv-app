import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import {
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Menu,
  TriangleAlert,
} from "lucide-react";
import type { MomentCalendarItem } from "../../api/generated/types.gen";
import { momentCalendarQuery, momentsQuery } from "../../api/query/options";
import { ListViewSwitch } from "../../components/journiv/ListViewSwitch";
import { moodColor } from "../../components/journiv/MomentMeta";
import { PageBar } from "../../components/journiv/PageBar";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Skeleton } from "../../components/ui/skeleton";
import { StatusView } from "../../components/journiv/StatusView";
import { cx } from "../../lib/cx";
import { todayInTimezone } from "../../lib/datetime";
import { useJournalLookup } from "../../lib/useJournalLookup";
import { useMoodLookup } from "../../lib/useMoodLookup";
import { useShell } from "../shell/AppShell";
import { MomentListItem } from "../timeline/MomentListItem";
import {
  buildMonthGrid,
  currentMonth,
  formatDayHeading,
  gridRange,
  isMonthKey,
  MONTH_NAMES,
  monthKeyOf,
  monthLabel,
  monthParts,
  shiftMonth,
  WEEKDAY_LABELS,
  yearOptions,
} from "./calendarGrid";
import "./calendar.css";

const viewerTimezone = () =>
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export function CalendarPane() {
  const params = useParams({ strict: false }) as {
    journalId?: string;
    momentId?: string;
  };
  const search = useSearch({ strict: false }) as {
    q?: string;
    month?: string;
    date?: string;
  };
  const shell = useShell();
  const navigate = useNavigate();
  const journals = useJournalLookup();
  const moods = useMoodLookup();
  const scopeJournal = journals.get(params.journalId);

  const timezone = viewerTimezone();
  const today = todayInTimezone(timezone);
  const month =
    search.month && isMonthKey(search.month)
      ? search.month
      : currentMonth(timezone);
  const { start, end } = gridRange(month);
  const cells = buildMonthGrid(month);
  const { year, monthIndex } = monthParts(month);
  const years = yearOptions(year);

  const calendar = useQuery(
    momentCalendarQuery({ journal_id: params.journalId, start, end }),
  );
  const byDay = new Map<string, MomentCalendarItem>(
    (calendar.data ?? []).map((item) => [item.logged_date_tz, item]),
  );

  const listRoute = params.journalId ? "/journals/$journalId" : "/timeline";
  const listParams = params.journalId
    ? { journalId: params.journalId }
    : undefined;
  const baseSearch = { q: search.q ?? "", view: "calendar" as const, month };

  const goToMonth = (next: string) =>
    navigate({
      to: listRoute,
      params: listParams,
      search: { q: search.q ?? "", view: "calendar", month: next },
      replace: true,
    });

  return (
    <section className="jv-shell__list" aria-label="Calendar">
      <PageBar
        className="jv-page-bar--compact-only"
        leading={
          <IconButton label="Open navigation" onClick={shell.openNavigation}>
            <Menu aria-hidden="true" size={19} />
          </IconButton>
        }
        title={
          <span className="jv-label jv-truncate">
            {scopeJournal?.title ?? "All journals"}
          </span>
        }
      />

      <header className="jv-list-header">
        <div className="jv-list-header__row">
          <h1 className="jv-display jv-list-header__title">
            <span className="jv-truncate">Calendar</span>
          </h1>
          <ListViewSwitch className="jv-list-header__switch" />
        </div>
        <div className="jv-calendar__nav">
          <IconButton
            label="Previous month"
            variant="ghost"
            onClick={() => goToMonth(shiftMonth(month, -1))}
          >
            <ChevronLeft aria-hidden="true" size={16} />
          </IconButton>
          <div className="jv-calendar__picker">
            <label className="sr-only" htmlFor="jv-calendar-month">
              Month
            </label>
            <select
              id="jv-calendar-month"
              className="jv-field jv-calendar__select"
              value={monthIndex}
              onChange={(event) =>
                goToMonth(monthKeyOf(year, Number(event.target.value)))
              }
            >
              {MONTH_NAMES.map((name, index) => (
                <option key={name} value={index}>
                  {name}
                </option>
              ))}
            </select>
            <label className="sr-only" htmlFor="jv-calendar-year">
              Year
            </label>
            <select
              id="jv-calendar-year"
              className="jv-field jv-calendar__select"
              value={year}
              onChange={(event) =>
                goToMonth(monthKeyOf(Number(event.target.value), monthIndex))
              }
            >
              {years.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <span className="sr-only" role="status" aria-live="polite">
            {monthLabel(month)}
          </span>
          <IconButton
            label="Next month"
            variant="ghost"
            onClick={() => goToMonth(shiftMonth(month, 1))}
          >
            <ChevronRight aria-hidden="true" size={16} />
          </IconButton>
          <Button
            variant="ghost"
            size="sm"
            className="jv-calendar__today"
            nativeButton={false}
            render={
              <Link
                to={listRoute}
                params={listParams}
                search={{
                  ...baseSearch,
                  month: today.slice(0, 7),
                  date: today,
                }}
                replace
              />
            }
          >
            Today
          </Button>
        </div>
      </header>

      <div className="jv-calendar__scroll">
        {calendar.isError ? (
          <StatusView
            role="alert"
            tone="danger"
            icon={<TriangleAlert size={20} />}
            title="The calendar could not be loaded"
            description="Check your connection and try again."
            action={
              <Button variant="secondary" onClick={() => calendar.refetch()}>
                Try again
              </Button>
            }
          />
        ) : (
          <>
            <div className="jv-calendar__grid">
              {WEEKDAY_LABELS.map((label) => (
                <div key={label} className="jv-calendar__weekday">
                  {label}
                </div>
              ))}
              {calendar.isLoading
                ? cells.map((cell) => (
                    <div key={cell.iso} className="jv-calendar__cell">
                      <Skeleton height="1.1rem" width="1.1rem" />
                    </div>
                  ))
                : cells.map((cell) => {
                    const item = byDay.get(cell.iso);
                    const mood = moods.get(item?.primary_mood_id);
                    const tint = mood ? moodColor(mood.color_value) : undefined;
                    const isToday = cell.iso === today;
                    const isSelected = cell.iso === search.date;
                    if (!item) {
                      return (
                        <div
                          key={cell.iso}
                          className={cx(
                            "jv-calendar__cell",
                            !cell.inMonth && "is-outside",
                            isToday && "is-today",
                          )}
                        >
                          <span className="jv-calendar__day">{cell.day}</span>
                        </div>
                      );
                    }
                    const countWord =
                      item.moment_count === 1 ? "moment" : "moments";
                    return (
                      <Link
                        key={cell.iso}
                        to={listRoute}
                        params={listParams}
                        search={{ ...baseSearch, date: cell.iso }}
                        replace
                        aria-label={`${formatDayHeading(cell.iso)}, ${item.moment_count} ${countWord}`}
                        aria-current={isSelected ? "date" : undefined}
                        className={cx(
                          "jv-calendar__cell",
                          "jv-calendar__cell--filled",
                          tint && "has-mood",
                          !cell.inMonth && "is-outside",
                          isToday && "is-today",
                          isSelected && "is-selected",
                        )}
                        style={
                          tint
                            ? ({ "--mood-accent": tint } as React.CSSProperties)
                            : undefined
                        }
                      >
                        {item.thumbnail_url && (
                          <span
                            className="jv-calendar__thumb"
                            style={{
                              backgroundImage: `url(${item.thumbnail_url})`,
                            }}
                            aria-hidden="true"
                          />
                        )}
                        <span className="jv-calendar__day" aria-hidden="true">
                          {cell.day}
                        </span>
                        <span className="jv-calendar__count" aria-hidden="true">
                          {item.moment_count}
                        </span>
                      </Link>
                    );
                  })}
            </div>

            {search.date && (
              <SelectedDay
                date={search.date}
                month={month}
                journalId={params.journalId}
                momentId={params.momentId}
                q={search.q ?? ""}
                journals={journals}
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}

function SelectedDay({
  date,
  month,
  journalId,
  momentId,
  q,
  journals,
}: {
  date: string;
  month: string;
  journalId?: string;
  momentId?: string;
  q: string;
  journals: ReturnType<typeof useJournalLookup>;
}) {
  const data = useInfiniteQuery(
    momentsQuery({ journal_id: journalId, start_date: date, end_date: date }),
  );
  const moments = data.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section
      className="jv-calendar__day-panel"
      aria-label={formatDayHeading(date)}
    >
      <h2 className="jv-section-title jv-calendar__day-heading">
        {formatDayHeading(date)}
      </h2>
      {data.isLoading && (
        <div className="jv-calendar__day-loading" role="status">
          <Skeleton height="3.5rem" />
          <Skeleton height="3.5rem" />
        </div>
      )}
      {data.isError && (
        <StatusView
          role="alert"
          tone="danger"
          icon={<TriangleAlert size={20} />}
          title="That day's moments could not be loaded"
          action={
            <Button variant="secondary" onClick={() => data.refetch()}>
              Try again
            </Button>
          }
        />
      )}
      {!data.isLoading && !data.isError && !moments.length && (
        <StatusView
          icon={<CalendarRange size={20} />}
          title="Nothing written this day"
        />
      )}
      {moments.map((moment) => (
        <MomentListItem
          key={moment.id}
          moment={moment}
          journal={journals.get(moment.entry?.journal_id)}
          journalId={journalId}
          selected={moment.id === momentId}
          search={q}
          view="calendar"
          month={month}
          date={date}
        />
      ))}
    </section>
  );
}
