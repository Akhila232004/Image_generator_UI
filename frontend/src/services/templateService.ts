export interface ReferenceForTemplate {
  type:
    | "image"
    | "gif"
    | "pdf"
    | "video"
    | "youtube"
    | "image-link";

  name: string;
  url: string;

  source?:
    | "input-folder"
    | "external-url"
    | "upload";

  mimeType?: string;
}


export interface GeneratedTemplate {
  template_id: string;
  version: string;
  name: string;

  canvas: {
    width: number;
    height: number;
    orientation: string;
    aspect_ratio: number;
  };

  layout: {
    type: string;
    alignment: string;
    preserve_reference_structure: boolean;
  };

  regions: Array<{
    name: string;
    x: number;
    y: number;
    width: number;
    height: number;
    order: number;
  }>;

  style: {
    keywords: string[];

    dominant_colors: Array<{
      hex: string;
      percentage: number;
    }>;

    average_brightness: number;
    preserve_reference_colors: boolean;
  };

  content: {
    keywords: string[];
    source_prompt: string;
  };

  reference_analysis: {
    width: number;
    height: number;
    format: string;
    mode: string;

    canvas: {
      width: number;
      height: number;
      aspect_ratio: number;
      orientation: string;
    };

    dominant_colors: Array<{
      hex: string;
      percentage: number;
    }>;

    average_brightness: number;
  };

  source?: {
    type: string;
    filename: string;
  };
}


export interface GenerateTemplateResponse {
  template_id: string;
  template_name: string;

  reference:
    GeneratedTemplate["reference_analysis"];

  prompt: {
    original_prompt: string;

    layout: {
      type: string;
      alignment: string;
      sections: string[];
    };

    style_keywords: string[];
    content_keywords: string[];
  };

  template: GeneratedTemplate;

  template_file: string;
}


const API_BASE_URL =
  "http://localhost:8000";


function getSourceType(
  reference: ReferenceForTemplate,
):
  | "input-folder"
  | "external-url"
  | "youtube" {

  if (reference.type === "youtube") {
    return "youtube";
  }

  if (
    reference.source ===
    "input-folder"
  ) {
    return "input-folder";
  }

  return "external-url";
}


function getSource(
  reference: ReferenceForTemplate,
): string {

  if (
    reference.source ===
    "input-folder"
  ) {
    return reference.name;
  }

  return reference.url;
}


function getErrorMessage(
  data: unknown,
): string {

  if (
    typeof data !== "object" ||
    data === null
  ) {
    return "Unable to generate template.";
  }

  const errorData = data as {
    detail?: unknown;
    message?: unknown;
  };

  if (Array.isArray(errorData.detail)) {

    const messages =
      errorData.detail
        .map((item) => {

          if (
            typeof item === "object" &&
            item !== null
          ) {

            const validationItem =
              item as {
                msg?: unknown;
                loc?: unknown[];
              };

            const message =
              typeof validationItem.msg ===
              "string"
                ? validationItem.msg
                : "Invalid request.";

            const location =
              Array.isArray(
                validationItem.loc,
              )
                ? validationItem.loc
                    .filter(
                      (part) =>
                        part !== "body",
                    )
                    .join(" → ")
                : "";

            return location
              ? `${location}: ${message}`
              : message;
          }

          return String(item);
        })
        .filter(Boolean);

    if (messages.length > 0) {
      return messages.join(" | ");
    }
  }

  if (
    typeof errorData.detail ===
    "string"
  ) {
    return errorData.detail;
  }

  if (
    typeof errorData.message ===
    "string"
  ) {
    return errorData.message;
  }

  return "Unable to generate template.";
}


export async function generateTemplate(
  reference: ReferenceForTemplate,
): Promise<GenerateTemplateResponse> {

  const source =
    getSource(reference);

  if (!source) {
    throw new Error(
      "Reference source is missing.",
    );
  }

  const formData =
    new FormData();

  formData.append(
    "source_type",
    getSourceType(reference),
  );

  formData.append(
    "source",
    source,
  );

  formData.append(
    "filename",
    reference.name ||
      "reference",
  );

  if (reference.mimeType) {
    formData.append(
      "content_type",
      reference.mimeType,
    );
  }

  const response =
    await fetch(
      `${API_BASE_URL}/api/templates/generate`,
      {
        method: "POST",
        body: formData,
      },
    );

  let data: unknown = null;

  try {
    data =
      await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    throw new Error(
      getErrorMessage(data),
    );
  }

  if (
    typeof data !== "object" ||
    data === null
  ) {
    throw new Error(
      "Invalid response received from the template service.",
    );
  }

  const responseData =
    data as {
      success?: boolean;
      template?:
        GenerateTemplateResponse;
    };

  if (!responseData.template) {
    throw new Error(
      "Template service returned an empty template.",
    );
  }

  return responseData.template;
}