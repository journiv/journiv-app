import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { journalAnalyticsQuery } from "../../api/query/options";
import { formatDateMedium } from "../../lib/datetime";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { SectionCard } from "./SectionCard";

const NUMBER = new Intl.NumberFormat();

export function JournalsTab() {
  const journals = useQuery(journalAnalyticsQuery());

  return (
    <div className="jv-insights__panel">
      <SectionCard
        title="Per journal"
        query={journals}
        isEmpty={(data) => data.journals.length === 0}
        emptyMessage="No journals yet."
      >
        {(data) => (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Journal</TableHead>
                <TableHead className="text-right">Entries</TableHead>
                <TableHead className="text-right">Words</TableHead>
                <TableHead className="text-right">Last entry</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.journals.map((journal) => (
                <TableRow key={journal.journal_id}>
                  <TableCell>
                    <Link
                      className="jv-insights__journal-link"
                      to="/journals/$journalId"
                      params={{ journalId: journal.journal_id }}
                      search={{ q: "" }}
                    >
                      {journal.title}
                    </Link>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {NUMBER.format(journal.entry_count)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {NUMBER.format(journal.total_words)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {journal.last_entry
                      ? formatDateMedium(journal.last_entry)
                      : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>
    </div>
  );
}
