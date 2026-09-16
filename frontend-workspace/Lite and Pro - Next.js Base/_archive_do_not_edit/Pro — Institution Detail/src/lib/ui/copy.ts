import type { InstitutionType } from "@/lib/api/types";
import type { LiteRiskStatus } from "./status";

function isHospital(type: InstitutionType | undefined): boolean {
  return type === "hospital";
}

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

  if (isHospital(type)) {
    return {
      title: "Air quality is expected to become unhealthy.",
      body: "Review operational readiness for indoor filtration and respiratory-care capacity.",
    };
  }

  return {
    title: "Air quality is expected to become unhealthy.",
    body: "Conditions around your school are expected to worsen. Review activity plans and indoor options.",
  };
}
