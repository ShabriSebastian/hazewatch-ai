import type { InstitutionType } from "@/lib/api/types";

const IMPROVING = "Conditions may improve gradually later in the day.";
const LEAD_LINE =
  "Air quality is expected to become unhealthy, especially during the forecast alert window.";

/**
 * Type-worded explanation for Institution Detail. All three contract types are
 * handled; see the note in `copy.ts` for why `authority` matters even though
 * Lite's selector does not currently offer it.
 */
export function getInstitutionDetailCopy(type: InstitutionType | undefined) {
  switch (type) {
    case "hospital":
      return {
        whatThisMeans: [
          LEAD_LINE,
          "Review indoor filtration readiness and respiratory-care capacity.",
          "Monitor conditions and be ready to adjust hospital operations if needed.",
        ],
        improving: IMPROVING,
      };
    case "authority":
      return {
        whatThisMeans: [
          LEAD_LINE,
          "Prepare public advisories and coordinate with school and clinic networks in the district.",
          "Monitor conditions and be ready to escalate if they worsen.",
        ],
        improving: IMPROVING,
      };
    case "school":
      return {
        whatThisMeans: [
          LEAD_LINE,
          "Reduce outdoor exposure for students and staff to help protect health.",
          "Monitor conditions and be ready to act if they worsen.",
        ],
        improving: IMPROVING,
      };
    default:
      return {
        whatThisMeans: [
          LEAD_LINE,
          "Reduce exposure for the people at this site.",
          "Monitor conditions and be ready to act if they worsen.",
        ],
        improving: IMPROVING,
      };
  }
}
