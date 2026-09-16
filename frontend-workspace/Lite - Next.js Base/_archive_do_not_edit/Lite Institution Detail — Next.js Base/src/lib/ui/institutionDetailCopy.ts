import type { InstitutionType } from "@/lib/api/types";

export function getInstitutionDetailCopy(type: InstitutionType | undefined) {
  if (type === "hospital") {
    return {
      whatThisMeans: [
        "Air quality is expected to become unhealthy, especially during the forecast alert window.",
        "Review indoor filtration readiness and respiratory-care capacity.",
        "Monitor conditions and be ready to adjust hospital operations if needed.",
      ],
      improving: "Conditions may improve gradually later in the day.",
    };
  }

  return {
    whatThisMeans: [
      "Air quality is expected to become unhealthy, especially during the forecast alert window.",
      "Reduce outdoor exposure for students and staff to help protect health.",
      "Monitor conditions and be ready to act if they worsen.",
    ],
    improving: "Conditions may improve gradually later in the day.",
  };
}
