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

  /*
   * This is primarily the preview URL used by the browser.
   *
   * IMPORTANT:
   * For Google Drive references this may be:
   *   http://localhost:8000/api/drive/file/...
   *
   * It must NOT be sent to the backend as the Drive source.
   * The actual Drive file ID is stored in sourceId.
   */
  url: string;

  source?:
    | "input-folder"
    | "external-url"
    | "upload"
    | "google-drive";

  /*
   * Real backend source identifier.
   *
   * Google Drive:
   *   sourceId = Google Drive file ID
   *
   * Manual upload:
   *   sourceId = uploaded filename
   *
   * Input folder:
   *   sourceId = filename
   *
   * External URL:
   *   sourceId = actual HTTP/HTTPS URL
   */
  sourceId?: string;

  mimeType?: string;
}


type BackendSourceType =
  | "input-folder"
  | "google-drive"
  | "upload"
  | "external-url"
  | "youtube";


function getSourceType(
  reference: PromptReference,
): BackendSourceType {

  /*
   * YouTube must be handled first because it is
   * a special external source type.
   */
  if (reference.type === "youtube") {
    return "youtube";
  }

  /*
   * Google Drive references must be sent as
   * google-drive, NOT external-url.
   */
  if (reference.source === "google-drive") {
    return "google-drive";
  }

  /*
   * Files coming from the old backend/input folder.
   */
  if (reference.source === "input-folder") {
    return "input-folder";
  }

  /*
   * Manually uploaded files are stored by the backend
   * in backend/manual_uploads.
   */
  if (reference.source === "upload") {
    return "upload";
  }

  /*
   * Everything else is an external HTTP/HTTPS source.
   */
  return "external-url";
}


function getSourceValue(
  reference: PromptReference,
): string {

  /*
   * ----------------------------------------------------
   * GOOGLE DRIVE
   * ----------------------------------------------------
   *
   * NEVER send reference.url here.
   *
   * reference.url is only the browser preview URL.
   *
   * The backend needs the actual Google Drive file ID.
   */
  if (reference.source === "google-drive") {

    const driveFileId =
      reference.sourceId?.trim();

    if (!driveFileId) {
      throw new Error(
        "Google Drive file ID is missing.",
      );
    }

    return driveFileId;
  }


  /*
   * ----------------------------------------------------
   * MANUAL UPLOAD
   * ----------------------------------------------------
   *
   * Send the filename stored by the backend.
   */
  if (reference.source === "upload") {

    const filename =
      reference.sourceId?.trim() ||
      reference.name?.trim();

    if (!filename) {
      throw new Error(
        "Uploaded file name is missing.",
      );
    }

    return filename;
  }


  /*
   * ----------------------------------------------------
   * INPUT FOLDER
   * ----------------------------------------------------
   *
   * Send the filename instead of the browser URL.
   */
  if (reference.source === "input-folder") {

    const filename =
      reference.sourceId?.trim() ||
      reference.name?.trim();

    if (!filename) {
      throw new Error(
        "Input file name is missing.",
      );
    }

    return filename;
  }


  /*
   * ----------------------------------------------------
   * EXTERNAL URL / YOUTUBE
   * ----------------------------------------------------
   *
   * For these sources we need the actual HTTP/HTTPS URL.
   *
   * sourceId is preferred because it stores the original
   * source instead of a browser-generated preview URL.
   */
  const url =
    reference.sourceId?.trim() ||
    reference.url?.trim();

  if (!url) {
    throw new Error(
      "Reference source is missing.",
    );
  }

  /*
   * Do not allow browser blob URLs to reach the backend.
   *
   * A blob URL exists only inside the browser and cannot
   * be downloaded by FastAPI.
   */
  if (
    url.startsWith("blob:")
  ) {
    throw new Error(
      "The browser preview URL cannot be used as the source. " +
      "Please reselect the reference.",
    );
  }

  /*
   * Validate external sources before sending them.
   */
  try {

    const parsedUrl =
      new URL(url);

    if (
      parsedUrl.protocol !== "http:" &&
      parsedUrl.protocol !== "https:"
    ) {
      throw new Error(
        "A valid HTTP or HTTPS URL is required.",
      );
    }

  } catch {

    throw new Error(
      "A valid HTTP or HTTPS URL is required.",
    );
  }

  return url;
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
    if (
      Array.isArray(
        errorData.detail,
      )
    ) {

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


      if (
        messages.length > 0
      ) {
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

  /*
   * ----------------------------------------------------
   * BASIC VALIDATION
   * ----------------------------------------------------
   */

  if (!reference) {

    throw new Error(
      "Please select a reference first.",
    );
  }


  /*
   * ----------------------------------------------------
   * DETERMINE BACKEND SOURCE TYPE
   * ----------------------------------------------------
   */

  let sourceType:
    | BackendSourceType;

  let source: string;

  try {

    sourceType =
      getSourceType(reference);

    source =
      getSourceValue(reference);

  } catch (error) {

    if (error instanceof Error) {
      throw error;
    }

    throw new Error(
      "Reference source is missing.",
    );
  }


  if (!source) {

    throw new Error(
      "Reference source is missing.",
    );
  }


  /*
   * ----------------------------------------------------
   * CREATE FORM DATA
   * ----------------------------------------------------
   */

  const formData =
    new FormData();


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


  /*
   * ----------------------------------------------------
   * DEBUG INFORMATION
   * ----------------------------------------------------
   *
   * This intentionally does NOT print API keys or
   * sensitive credentials.
   *
   * It is useful for confirming that a Drive reference
   * is being sent correctly.
   */
  console.log(
    "Generating AI prompt:",
    {
      sourceType,
      source:
        sourceType === "google-drive"
          ? "Google Drive file ID"
          : source,
      filename:
        reference.name,
      contentType:
        reference.mimeType,
    },
  );


  /*
   * ----------------------------------------------------
   * CALL BACKEND
   * ----------------------------------------------------
   */

  try {

    const response =
      await fetch(
        `${API_BASE_URL}/api/prompts/generate`,
        {
          method: "POST",
          body: formData,
        },
      );


    /*
     * ------------------------------------------------
     * READ RESPONSE
     * ------------------------------------------------
     */

    let data: unknown = null;


    try {

      data =
        await response.json();

    } catch {

      data = null;
    }


    /*
     * ------------------------------------------------
     * HANDLE HTTP ERRORS
     * ------------------------------------------------
     */

    if (!response.ok) {

      throw new Error(
        getErrorMessage(data),
      );
    }


    /*
     * ------------------------------------------------
     * VALIDATE RESPONSE OBJECT
     * ------------------------------------------------
     */

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


    /*
     * ------------------------------------------------
     * VALIDATE GENERATED PROMPT
     * ------------------------------------------------
     */

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

    if (
      error instanceof Error
    ) {

      throw error;
    }


    throw new Error(
      "Unable to generate a prompt with AI.",
    );
  }
}