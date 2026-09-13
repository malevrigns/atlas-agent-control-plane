import { Hono } from "hono";

import { FileService } from "../../../application/file-service.js";
import { AppError, ok } from "../../../core/errors.js";

export function fileRoutes(files: FileService) {
  const router = new Hono();

  router.post("/", async (c) => {
    const body = await c.req.parseBody();
    const upload = body.upload;
    if (!isFile(upload)) {
      throw new AppError("upload is required", { code: 400, statusCode: 400 });
    }
    const bytes = new Uint8Array(await upload.arrayBuffer());
    const saved = await files.saveUpload({
      name: upload.name,
      type: upload.type,
      data: bytes,
    });
    return c.json(ok(saved.file));
  });

  router.get("/:fileId/preview", async (c) => {
    const preview = await files.preview(c.req.param("fileId"));
    return c.json(ok(preview));
  });

  router.get("/:fileId/download", async (c) => {
    const file = await files.readBytes(c.req.param("fileId"));
    return new Response(file.bytes, {
      headers: {
        "Content-Type": file.type,
        "Content-Disposition": `attachment; filename="${file.name}"`,
      },
    });
  });

  return router;
}

function isFile(value: unknown): value is File {
  return Boolean(value) && typeof value === "object" && typeof (value as File).arrayBuffer === "function";
}
