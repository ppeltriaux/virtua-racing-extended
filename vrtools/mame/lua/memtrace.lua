-- Memory tracer: read/write taps with the V60 PC, aggregated per frame per (pc, addr & ~0xff), plus RAM dumps.
-- Env: VR_TRACE_LOG (absolute path), VR_TRACE_FROM/VR_TRACE_TO (frame window [from, to)),
--      VR_TRACE_READ / VR_TRACE_WRITE ("start-end,start-end" hex, V60 addresses), VR_TRACE_DUMP ("f1,f2,...").
local log_path = os.getenv("VR_TRACE_LOG")
if log_path then
  local out = assert(io.open(log_path, "w"))
  local from = tonumber(os.getenv("VR_TRACE_FROM") or "0")
  local amask = os.getenv("VR_TRACE_FINE") and 0xffffff or 0xffff00   -- VR_TRACE_FINE=1: exact addresses instead of 256-byte pages
  local to = tonumber(os.getenv("VR_TRACE_TO") or "999999")
  local cpu = manager.machine.devices[":maincpu"]
  local mem = cpu.spaces["program"]
  local frame, bank, events = 0, 0, 0
  local reads, writes = {}, {}
  local taps = {}
  _G.vr_trace_taps = taps          -- keep tap objects reachable: a collected tap is removed by MAME
  local function ranges(s)
    local r = {}
    for a, b in string.gmatch(s or "", "(%x+)%-(%x+)") do r[#r + 1] = {tonumber(a, 16), tonumber(b, 16)} end
    return r
  end
  local dumps = {}
  for f in string.gmatch(os.getenv("VR_TRACE_DUMP") or "", "%d+") do dumps[tonumber(f)] = true end
  for _, r in ipairs(ranges(os.getenv("VR_TRACE_READ"))) do
    taps[#taps + 1] = mem:install_read_tap(r[1], r[2], "trace_r", function(offset, data, mask)
      if frame >= from and frame < to then
        local key = (cpu.state["PC"].value << 24) | (offset & amask)
        reads[key] = (reads[key] or 0) + 1
      end
    end)
  end
  for _, r in ipairs(ranges(os.getenv("VR_TRACE_WRITE"))) do
    taps[#taps + 1] = mem:install_write_tap(r[1], r[2], "trace_w", function(offset, data, mask)
      if frame >= from and frame < to then
        local key = (cpu.state["PC"].value << 24) | (offset & amask)
        writes[key] = (writes[key] or 0) + 1
      end
    end)
  end
  taps[#taps + 1] = mem:install_write_tap(0xe00004, 0xe00005, "trace_bank", function(offset, data, mask)
    if (data & 0xf) == 1 then
      local b = (data >> 4) & 7
      if b ~= bank then bank = b; out:write(string.format("B %d %d\n", frame, bank)) end
    end
  end)
  local function flush()
    for key, n in pairs(reads) do
      out:write(string.format("R %d %x %x %d %d\n", frame, key >> 24, key & 0xffffff, bank, n)); events = events + n
    end
    for key, n in pairs(writes) do
      out:write(string.format("W %d %x %x %d\n", frame, key >> 24, key & 0xffffff, n)); events = events + n
    end
    reads, writes = {}, {}
  end
  local traced = 0
  -- END lines are checkpoints (the parser accepts several and uses the last): written when the window
  -- closes and after every dump, because MAME's stop notifier is not reliable under -str.
  local function checkpoint() out:write(string.format("END %d %d\n", traced, events)); out:flush() end
  checkpoint()        -- a log is parseable even if the window never fires and no dump is requested
  emu.register_frame_done(function()
    if frame >= from and frame < to then
      local ok, err = pcall(flush)
      if not ok then out:write("E " .. frame .. " " .. tostring(err) .. "\n"); out:flush() end
      traced = traced + 1
    end
    if dumps[frame] then
      local p = string.format("%s.ram.%d.bin", log_path, frame)
      local f = assert(io.open(p, "wb")); f:write(mem:read_range(0x500000, 0x53ffff, 8)); f:close()
      local p2 = string.format("%s.nvram.%d.bin", log_path, frame)      -- RAMA / NVRAM area (entity pool lives here)
      local f2 = assert(io.open(p2, "wb")); f2:write(mem:read_range(0x400000, 0x40ffff, 8)); f2:close()
      out:write(string.format("D %d %s\n", frame, p)); checkpoint()
    end
    frame = frame + 1
    if frame == to then checkpoint() end
  end)
end
