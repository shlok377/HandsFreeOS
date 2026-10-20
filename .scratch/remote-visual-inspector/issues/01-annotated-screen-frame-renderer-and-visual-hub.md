# 01: Annotated Screen Frame Renderer & Visual Hub

**What to build:** A decoupled, thread-safe visual snapshot and annotation engine that ingests raw screen captures and YOLO `BoundingBox` detections, draws bounding boxes, IDs, labels, and confidence tags, and maintains a thread-safe latest-frame buffer with rolling latency and timestamp metadata for streaming consumers.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `VisualStreamHub` manages the latest annotated frame, raw dimensions, and active bounding box metadata in a thread-safe manner.
- [x] Element bounding boxes are rendered with colored borders, numeric labels, and confidence overlays.
- [x] Fallback test/dummy frame generation is provided when running without active Hyprland/grim display or without GPU YOLO weights.
- [x] Unit tests verify thread-safe frame updates, bounding box annotations, and frame encoding under `<20ms` processing overhead.
