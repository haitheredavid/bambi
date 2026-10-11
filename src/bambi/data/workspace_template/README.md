# {{name}}

bambi print workspace: one folder per print under `sessions/`. Created by `bambi workspace init`; the tool, skills and docs live in [bambi](https://github.com/haitheredavid/bambi).

```
bambi new <name>          # sessions/YYYY-MM-DD-<name>/ with model.blend
bambi blender open <s>    # model it (Blender MCP bridge on :9876)
bambi build <s> --strict  # export, check, slice
bambi studio <s>          # print via Bambu Cloud
```

`profiles/` holds overrides of the profiles bambi ships (`bambi profiles sync`). `assets/studio.blend` is the render studio, built on first `bambi render`.

## Gallery

<!-- gallery:start -->
<!-- gallery:end -->
