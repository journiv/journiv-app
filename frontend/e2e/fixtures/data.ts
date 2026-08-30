import type { Client } from "@/api/generated/client";
import {
  bulkAddTagsToMomentApiV1MomentsMomentIdTagsPost,
  createJournalApiV1JournalsPost,
  createMomentApiV1MomentsPost,
} from "@/api/generated";
import type {
  JournalResponse,
  MomentResponse,
} from "@/api/generated/types.gen";
import { FROZEN_NOW } from "./determinism";

/** The timezone the whole suite runs in. Matches `playwright.config.ts`, so a
 *  moment created here lands on the day the browser renders. */
export const TEST_TIMEZONE = "America/Los_Angeles";

function unwrap<T>(
  result: { data?: T; error?: unknown; response?: Response },
  what: string,
): T {
  if (result.error !== undefined || result.data === undefined)
    throw new Error(
      `[e2e] Test setup failed: ${what} returned HTTP ${result.response?.status}. ` +
        `Setup uses the API precisely so this failure is unambiguous — the ` +
        `feature under test is probably fine.`,
    );
  return result.data;
}

/** Creates the state a test needs, over the API.
 *
 *  The rule this exists to enforce: build prerequisites through the API, and use
 *  the browser only for the behaviour you are actually asserting. A test about
 *  editing an entry should not spend thirty seconds clicking one into existence.
 *
 *  There is no cleanup here on purpose. The worker's whole account is deleted at
 *  teardown, and that cascade removes everything below it — so nothing has to be
 *  registered, tracked, or remembered.
 */
export class DataFactory {
  constructor(
    private readonly client: Client,
    /** Prefix derived from the running test, so data is traceable in a failure
     *  screenshot and two tests in one worker never collide by name. */
    private readonly prefix: string,
  ) {}

  label(name: string): string {
    return `${this.prefix} ${name}`;
  }

  async journal(
    options: { title?: string; description?: string } = {},
  ): Promise<JournalResponse> {
    const result = await createJournalApiV1JournalsPost({
      client: this.client,
      body: {
        title: options.title ?? this.label("Journal"),
        description: options.description ?? null,
      },
    });
    return unwrap(result, "POST /api/v1/journals");
  }

  async moment(options: {
    journalId: string;
    title?: string;
    /** Plain body text. Quill stores a delta; this wraps the common case. */
    body?: string;
    /** Defaults to the suite's frozen clock so the moment lands on "today". */
    loggedAt?: Date;
  }): Promise<MomentResponse> {
    const body = options.body ?? this.label("body text");
    const result = await createMomentApiV1MomentsPost({
      client: this.client,
      body: {
        logged_at_utc: (options.loggedAt ?? FROZEN_NOW).toISOString(),
        logged_timezone: TEST_TIMEZONE,
        entry: {
          journal_id: options.journalId,
          title: options.title ?? this.label("Entry"),
          content_delta: { ops: [{ insert: `${body}\n` }] },
        },
      },
    });
    return unwrap(result, "POST /api/v1/moments");
  }

  /** Attaches tags to a moment, creating any that do not exist. */
  async tags(momentId: string, names: string[]): Promise<void> {
    const result = await bulkAddTagsToMomentApiV1MomentsMomentIdTagsPost({
      client: this.client,
      path: { moment_id: momentId },
      body: names,
    });
    unwrap(result, `POST /api/v1/moments/${momentId}/tags`);
  }
}
