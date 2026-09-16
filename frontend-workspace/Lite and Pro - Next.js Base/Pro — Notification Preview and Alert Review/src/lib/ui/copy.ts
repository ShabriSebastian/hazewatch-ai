import type { InstitutionType } from "@/lib/api/types";
import type { LiteRiskStatus } from "./status";

/**
 * Institution type changes the WORDING only — never a threshold, never whether
 * an alert fires. A school, a hospital and a district authority all alert on
 * the same air at the same 35.5 µg/m³; what differs is what they do about it.
 *
 * All three contract types are handled explicitly. `authority` was easy to miss
 * because Lite's selector currently offers only schools and hospitals, but the
 * type is first-class in the contract and the backend raises real alerts for
 * both authority sites — telling a provincial disaster-management agency to
 * "review activity plans around your school" would be visibly wrong the moment
 * that filter changed.
 */
export function getStatusCopy(type: InstitutionType | undefined, status: LiteRiskStatus) {
  if (status === "safe") {
    return {
      title: "Air quality is normal.",
      body: "No action is needed.",
    };
  }

  if (status === "watch") {
    return {
      title: "Conditions are being monitored.",
      body: "No action is needed right now. Conditions may change, and we’ll notify you if the status rises to Alert.",
    };
  }

  const title = "Air quality is expected to become unhealthy.";

  switch (type) {
    case "hospital":
      return {
        title,
        body: "Review operational readiness for indoor filtration and respiratory-care capacity.",
      };
    case "authority":
      return {
        title,
        body: "Review district advisory plans and coordination with school and clinic networks.",
      };
    case "school":
      return {
        title,
        body: "Conditions around your school are expected to worsen. Review activity plans and indoor options.",
      };
    default:
      // An institution type the contract adds later. Say the true, general
      // thing rather than guessing at an audience we were not told about.
      return {
        title,
        body: "Review your preparedness plans for the affected period.",
      };
  }
}

/**
 * One-line "what this means", worded for the audience. All three contract
 * types handled; `authority` is first-class even though Lite's selector does
 * not currently offer it.
 */
export function getWhatThisMeansLine(type: InstitutionType | undefined): string {
  switch (type) {
    case "hospital":
      return "Operational readiness may need to be adjusted.";
    case "authority":
      return "District advisories and coordination may need to be issued.";
    case "school":
      return "Outdoor activities may need to be adjusted.";
    default:
      return "Preparedness plans may need to be adjusted.";
  }
}
