const API_BASE_URL = "http://localhost:8000";

export interface PromptReference {
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


function getSourceType(
  reference: PromptReference,
): "input-folder" | "external-url" | "youtube" {

  if (reference.type === "youtube") {
    return "youtube";
  }

  if (
    reference.source === "input-folder"
  ) {
    return "input-folder";
  }

  return "external-url";
}


function getSourceValue(
  reference: PromptReference,
): string {

  /*
   * For files that already exist inside backend/input,
   * send the filename instead of the localhost URL.
   *
   * This avoids the browser-side CORS problem.
   */
  if (
    reference.source === "input-folder"
  ) {
    return reference.name;
  }

  /*
   * For external references, send the actual URL.
   */
  return reference.url;
}


function getErrorMessage(
  data: unknown,
): string {

  if (!data) {
    return "Unable to generate a prompt with AI.";
  }

  if (
    typeof data === "object" &&
    data !== null
  ) {

    const errorData =
      data as {
        detail?: unknown;
        message?: unknown;
      };

    /*
     * FastAPI validation errors normally return:
     *
     * {
     *   "detail": [
     *     {
     *       "type": "...",
     *       "loc": [...],
     *       "msg": "..."
     *     }
     *   ]
     * }
     */

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
  }

  return "Unable to generate a prompt with AI.";
}


export async function generatePrompt(
  reference: PromptReference,
): Promise<string> {

  if (!reference) {
    throw new Error(
      "Please select a reference first.",
    );
  }

  const sourceType =
    getSourceType(reference);

  const source =
    getSourceValue(reference);

  if (!source) {
    throw new Error(
      "Reference source is missing.",
    );
  }

  const formData = new FormData();

  formData.append(
    "source_type",
    sourceType,
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

  try {

    const response = await fetch(
      `${API_BASE_URL}/api/prompts/generate`,
      {
        method: "POST",
        body: formData,
      },
    );

    let data: unknown = null;

    try {
      data = await response.json();
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
        "Invalid response received from the AI prompt service.",
      );
    }

    const responseData =
      data as {
        success?: boolean;
        prompt?: string;
      };

    if (
      !responseData.prompt ||
      !responseData.prompt.trim()
    ) {
      throw new Error(
        "AI returned an empty prompt.",
      );
    }

    return responseData.prompt.trim();

  } catch (error) {

    if (error instanceof Error) {
      throw error;
    }

    throw new Error(
      "Unable to generate a prompt with AI.",
    );
  }
}