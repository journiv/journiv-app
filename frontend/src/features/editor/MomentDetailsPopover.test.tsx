import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client/api";
import type {
  MomentResponse,
  WeatherData,
} from "../../api/generated/types.gen";
import {
  formatWeatherSummary,
  MomentDetailsPanel,
  type MomentDetailsPanelProps,
} from "./MomentDetailsPopover";

vi.mock("../../api/client/api", () => ({
  api: {
    moods: vi.fn(),
    people: vi.fn(),
    searchTags: vi.fn(),
    searchLocation: vi.fn(),
    reverseGeocode: vi.fn(),
    fetchWeather: vi.fn(),
    updateMoment: vi.fn(),
    addMomentTags: vi.fn(),
    removeMomentTag: vi.fn(),
    setMomentPeople: vi.fn(),
  },
}));

type GeoOk = (position: {
  coords: { latitude: number; longitude: number };
}) => void;
type GeoErr = (error: { code: number; message: string }) => void;

function stubGeolocation(getCurrentPosition: (ok: GeoOk, err: GeoErr) => void) {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition: vi.fn(getCurrentPosition) },
  });
}
afterEach(() => {
  // jsdom ships no geolocation; leave it that way between tests.
  Reflect.deleteProperty(navigator, "geolocation");
});

const moment = (over: Partial<MomentResponse> = {}): MomentResponse =>
  ({
    id: "moment-1",
    user_id: "u1",
    logged_at_utc: "2026-08-26T10:00:00Z",
    logged_date_tz: "2026-08-26",
    logged_timezone: "UTC",
    tags: [],
    people: [],
    ...over,
  }) as MomentResponse;

function setup(props: Partial<MomentDetailsPanelProps> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const onSaved = props.onSaved ?? vi.fn();
  const ensureMomentId = props.ensureMomentId ?? vi.fn(async () => "moment-1");
  render(
    <MomentDetailsPanel
      moment={moment()}
      ensureMomentId={ensureMomentId}
      onSaved={onSaved}
      loggedAtUtc="2026-08-26T10:00:00Z"
      loggedTimezone="UTC"
      {...props}
    />,
    { wrapper },
  );
  return { onSaved, ensureMomentId };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.moods).mockResolvedValue([
    {
      id: "mood-happy",
      name: "Happy",
      category: "positive",
      score: 5,
      color_value: 0xff405de6,
      created_at: "",
      updated_at: "",
    },
  ] as never);
  vi.mocked(api.people).mockResolvedValue([
    {
      id: "person-1",
      name: "Sam",
      created_at: "",
      updated_at: "",
      user_id: "u1",
    },
  ] as never);
  vi.mocked(api.searchTags).mockResolvedValue([]);
  vi.mocked(api.reverseGeocode).mockResolvedValue({
    name: "Kyoto, Japan",
    latitude: 35,
    longitude: 135,
    locality: "Kyoto",
    country: "Japan",
    timezone: "Asia/Tokyo",
  } as never);
  vi.mocked(api.updateMoment).mockResolvedValue(moment());
  vi.mocked(api.addMomentTags).mockResolvedValue([]);
  vi.mocked(api.removeMomentTag).mockResolvedValue(undefined as never);
  vi.mocked(api.setMomentPeople).mockResolvedValue([]);
});

describe("formatWeatherSummary", () => {
  it("renders condition and rounded Celsius", () => {
    expect(
      formatWeatherSummary({ condition: "Clear", temp_c: 13.6 } as WeatherData),
    ).toBe("Clear 14°C");
  });
});

describe("MomentDetailsPanel", () => {
  it("saves the primary mood through PUT /moments/{id}", async () => {
    const { onSaved } = setup();
    await userEvent.click(await screen.findByRole("button", { name: /Happy/ }));
    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith("moment-1", {
        primary_mood_id: "mood-happy",
      }),
    );
    expect(onSaved).toHaveBeenCalledWith("moment-1");
  });

  it("clears the mood with the None option", async () => {
    setup({ moment: moment({ primary_mood_id: "mood-happy" }) });
    await userEvent.click(await screen.findByRole("button", { name: "None" }));
    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith("moment-1", {
        primary_mood_id: null,
      }),
    );
  });

  it("adds a tag by name and reports failures on screen", async () => {
    setup();
    await userEvent.type(screen.getByLabelText("Add a tag"), "travel");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(api.addMomentTags).toHaveBeenCalledWith("moment-1", ["travel"]),
    );

    vi.mocked(api.addMomentTags).mockRejectedValueOnce(new Error("boom"));
    await userEvent.type(screen.getByLabelText("Add a tag"), "family");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(
      await screen.findByText("Tag couldn't be added. Try again."),
    ).toBeTruthy();
  });

  it("removes an existing tag by id", async () => {
    setup({
      moment: moment({ tags: [{ id: "t1", name: "travel" } as never] }),
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Remove travel" }),
    );
    await waitFor(() =>
      expect(api.removeMomentTag).toHaveBeenCalledWith("moment-1", "t1"),
    );
  });

  it("toggles a person and PUTs the full id set", async () => {
    setup();
    await userEvent.click(await screen.findByLabelText("Sam"));
    await waitFor(() =>
      expect(api.setMomentPeople).toHaveBeenCalledWith("moment-1", [
        "person-1",
      ]),
    );
  });

  it("geocodes a place and saves the chosen result", async () => {
    vi.mocked(api.searchLocation).mockResolvedValue({
      provider: "nominatim",
      results: [
        {
          name: "Kyoto, Japan",
          latitude: 35,
          longitude: 135,
          locality: "Kyoto",
          admin_area: null,
          country: "Japan",
          timezone: "Asia/Tokyo",
        },
      ],
    } as never);
    setup();
    await userEvent.type(screen.getByLabelText("Search for a place"), "Kyoto");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Kyoto, Japan" }),
    );
    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith(
        "moment-1",
        expect.objectContaining({
          latitude: 35,
          longitude: 135,
          location_json: expect.objectContaining({ name: "Kyoto, Japan" }),
        }),
      ),
    );
  });

  it("uses the device location: detects, reverse-geocodes, saves place and weather", async () => {
    stubGeolocation((ok) => ok({ coords: { latitude: 35, longitude: 135 } }));
    vi.mocked(api.fetchWeather).mockResolvedValue({
      provider: "openweather",
      timestamp: "2026-08-26T10:00:00Z",
      weather: { condition: "Rain", temp_c: 18.2, temp_f: 65 },
    } as never);
    setup();

    await userEvent.click(
      screen.getByRole("button", { name: "Use current location" }),
    );

    await waitFor(() =>
      expect(api.reverseGeocode).toHaveBeenCalledWith(35, 135),
    );
    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith(
        "moment-1",
        expect.objectContaining({
          latitude: 35,
          longitude: 135,
          location_json: expect.objectContaining({ name: "Kyoto, Japan" }),
        }),
      ),
    );
    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith(
        "moment-1",
        expect.objectContaining({ weather_summary: "Rain 18°C" }),
      ),
    );
  });

  it("surfaces a denied geolocation permission and saves nothing", async () => {
    stubGeolocation((_ok, err) => err({ code: 1, message: "denied" }));
    setup();

    await userEvent.click(
      screen.getByRole("button", { name: "Use current location" }),
    );

    expect(
      await screen.findByText(/location permission was denied/i),
    ).toBeTruthy();
    expect(api.updateMoment).not.toHaveBeenCalled();
    expect(api.reverseGeocode).not.toHaveBeenCalled();
  });

  it("falls back to a coordinate label when reverse geocoding fails", async () => {
    stubGeolocation((ok) =>
      ok({ coords: { latitude: 12.5, longitude: -8.25 } }),
    );
    vi.mocked(api.reverseGeocode).mockRejectedValue(new Error("offline"));
    vi.mocked(api.fetchWeather).mockResolvedValue({
      enabled: false,
      message: "off",
    } as never);
    setup();

    await userEvent.click(
      screen.getByRole("button", { name: "Use current location" }),
    );

    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith(
        "moment-1",
        expect.objectContaining({
          latitude: 12.5,
          longitude: -8.25,
          location_json: expect.objectContaining({ name: "12.5000, -8.2500" }),
        }),
      ),
    );
  });

  it("reports when the weather service is disabled without saving", async () => {
    vi.mocked(api.fetchWeather).mockResolvedValue({
      enabled: false,
      message: "Weather lookup is turned off on this server.",
    } as never);
    setup({ moment: moment({ latitude: 35, longitude: 135 }) });
    await userEvent.click(
      screen.getByRole("button", { name: "Fetch for this location" }),
    );
    expect(
      await screen.findByText("Weather lookup is turned off on this server."),
    ).toBeTruthy();
    expect(api.updateMoment).not.toHaveBeenCalled();
  });

  it("fetches weather and stores a summary when coordinates exist", async () => {
    vi.mocked(api.fetchWeather).mockResolvedValue({
      provider: "openweather",
      timestamp: "2026-08-26T10:00:00Z",
      weather: { condition: "Rain", temp_c: 18.2, temp_f: 65 },
    } as never);
    setup({ moment: moment({ latitude: 35, longitude: 135 }) });
    await userEvent.click(
      screen.getByRole("button", { name: "Fetch for this location" }),
    );
    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith(
        "moment-1",
        expect.objectContaining({ weather_summary: "Rain 18°C" }),
      ),
    );
  });

  it("does not offer an automatic fetch without coordinates", () => {
    setup({ moment: moment({ latitude: null, longitude: null }) });
    expect(
      screen.queryByRole("button", { name: "Fetch for this location" }),
    ).toBeNull();
    expect(
      screen.getByText("Add a location to fetch weather automatically."),
    ).toBeTruthy();
  });

  it("creates the draft Moment on first write for a new entry", async () => {
    const ensureMomentId = vi.fn(async () => "draft-moment");
    setup({ moment: undefined, ensureMomentId });
    await userEvent.click(await screen.findByRole("button", { name: /Happy/ }));
    await waitFor(() => expect(ensureMomentId).toHaveBeenCalled());
    await waitFor(() =>
      expect(api.updateMoment).toHaveBeenCalledWith("draft-moment", {
        primary_mood_id: "mood-happy",
      }),
    );
  });

  it("stays silent at the section level when no Journal is chosen yet", async () => {
    const ensureMomentId = vi.fn(async () => null);
    setup({ moment: undefined, ensureMomentId });
    await userEvent.click(await screen.findByRole("button", { name: /Happy/ }));
    await waitFor(() => expect(ensureMomentId).toHaveBeenCalled());
    expect(screen.queryByText("Mood couldn't be saved. Try again.")).toBeNull();
  });
});
