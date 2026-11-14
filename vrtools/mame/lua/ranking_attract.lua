-- Phase 27 Task 3: a boot and the attract mode, no input: the battery RAM's writes from the first instruction, the modes, and each
-- ranking page's frames, rows and title. Env:
--   VR_RANK_LOG    the log (required)
--   VR_RANK_TAP    "lo-hi" (hex): a write tap on that range, installed when the script loads (before the boot's S-RAM check runs)
--   VR_RANK_SNAPS  "id,id,...": a snapshot (MAME's snapshot directory) PAGE_SNAP frames after the first frame of the first page
--                  that shows each of these ranking ids (the shown id 0x40fc69), once an id
--   VR_RANK_POKE   "frame:address=hexbytes;...": bytes written into the battery RAM (0x400000..0x40ffff, through MAME's nvram share,
--                  so no W line) at that frame end, then read back through the CPU's bus (a K line)
--   VR_RANK_INPUT  "frame:field:frames;...": a button of :IN.0 / :IN.1 by its MAME name ("Service Mode", "VR1 (Red)", "VR4
--                  (Green)", ...) held from that frame end for that many frames (the test mode: Service Mode enters it, Red moves
--                  the cursor, Green chooses)
-- Lines (hex but the frames and the state):
--   W <frame> <pc> <address> <data> <mask>     a write in VR_RANK_TAP (the bus is 16 bits wide: an even address, the mask names
--                                              the bytes written); frame 0 is before the first frame end
--   M <frame> <mode 0x501139> <state 0x501180> <flag>     every frame end at which one of them changes (the flag: the direction
--                                              byte 0x502294)
--   P <frame> <shown id> <data index 0x501934> <table 0x5018f0> <first entry shown +0x36>     every frame end in mode 0x03
--                                              state 3 (the page: recon §3) at which one of them changes
--   T <frame> <62 words>                       the title row (0x700200) at a frame end in mode 0x03 state 3 when it changes
--   B <frame> <row 1..6: the distinct words of its three tile rows' 62 columns, '/' between rows>   in mode 0x03 state 3 when it
--                                              changes (the page's rows: the first at 0x702580, 0x200 bytes a row, 0x80 a tile row)
--   S <frame> <id>                             a snapshot (VR_RANK_SNAPS)
--   I <frame> <field>                          a button pressed (VR_RANK_INPUT)
--   K <frame> <address> <hexbytes>             a poke (VR_RANK_POKE) read back through the CPU's bus right after it was written
local out = assert(io.open(assert(os.getenv("VR_RANK_LOG"), "ranking_attract.lua: VR_RANK_LOG is not set"), "w"))
local cpu = manager.machine.devices[":maincpu"]
local mem = cpu.spaces["program"]
local PAGE_SNAP = 200                        -- into the page's first screen (264 frames shown, then 132 wiping out: recon §3)
local frame = 0
local lo, hi = string.match(os.getenv("VR_RANK_TAP") or "", "^(%x+)-(%x+)$")
_G.vr_rank_taps = {}
if lo then
  _G.vr_rank_taps[1] = mem:install_write_tap(tonumber(lo, 16), tonumber(hi, 16), "vr_rank", function(offset, data, mask)
    out:write(string.format("W %d %x %x %x %x\n", frame, cpu.state["PC"].value, offset, data, mask))
  end)
end
local want = {}
for id in string.gmatch(os.getenv("VR_RANK_SNAPS") or "", "%d+") do want[tonumber(id)] = true end
local nvram = manager.machine.memory.shares[":nvram"]
local pokes = {}
for f, a, hex in string.gmatch(os.getenv("VR_RANK_POKE") or "", "(%d+):(%x+)=(%x+)") do
  pokes[#pokes + 1] = {tonumber(f), tonumber(a, 16), hex}
end
local function field(name)
  for _, tag in ipairs({":IN.0", ":IN.1"}) do
    for n, f in pairs(manager.machine.ioport.ports[tag].fields) do if n == name then return f end end
  end
  error("ranking_attract.lua: no button " .. name)
end
local presses = {}
for f, name, hold in string.gmatch(os.getenv("VR_RANK_INPUT") or "", "(%d+):([^:;]+):(%d+)") do
  presses[#presses + 1] = {tonumber(f), field(name), tonumber(hold), name}
end
local last_m, last_p, last_t, last_b, page_at, snap_at, snap_id = "", "", "", "", nil, nil, nil

local function words(addr, n)
  local w = {}
  for c = 0, n - 1 do w[#w + 1] = string.format("%04x", mem:read_u16(addr + 2 * c)) end
  return w
end

local function rows()
  local r = {}
  for k = 0, 5 do
    local seen, list = {}, {}
    for line = 0, 2 do
      for _, w in ipairs(words(0x702580 + 0x200 * k + 0x80 * line, 62)) do
        if not seen[w] then seen[w] = true; list[#list + 1] = w end
      end
    end
    table.sort(list)
    r[#r + 1] = table.concat(list, ",")
  end
  return table.concat(r, "/")
end

emu.register_frame_done(function()
  frame = frame + 1
  for _, p in ipairs(pokes) do
    if p[1] == frame then
      local k = 0
      for b in string.gmatch(p[3], "%x%x") do nvram:write_u8(p[2] - 0x400000 + k, tonumber(b, 16)); k = k + 1 end
      local back = {}
      for j = 0, k - 1 do back[#back + 1] = string.format("%02x", mem:read_u8(p[2] + j)) end
      out:write(string.format("K %d %x %s\n", frame, p[2], table.concat(back)))
    end
  end
  for _, p in ipairs(presses) do
    if p[1] == frame then p[2]:set_value(1); out:write(string.format("I %d %s\n", frame, p[4])) end
    if p[1] + p[3] == frame then p[2]:set_value(0) end
  end
  local mode, state, flag = mem:read_u8(0x501139), mem:read_u8(0x501180), mem:read_u8(0x502294)
  local m = string.format("%x %d %x", mode, state, flag)
  if m ~= last_m then out:write(string.format("M %d %s\n", frame, m)); last_m = m end
  if mode == 3 and state == 3 then
    local e = mem:read_u32(0x501314)
    local id = mem:read_u8(0x40fc69)
    local p = string.format("%d %d %x %x", id, mem:read_u8(0x501934), mem:read_u32(0x5018f0), mem:read_u8(e + 0x36))
    if p ~= last_p then out:write(string.format("P %d %s\n", frame, p)); last_p = p end
    local t = table.concat(words(0x700200, 62))
    if t ~= last_t then out:write(string.format("T %d %s\n", frame, t)); last_t = t end
    local b = rows()
    if b ~= last_b then out:write(string.format("B %d %s\n", frame, b)); last_b = b end
    if not page_at then
      page_at = frame
      if want[id] then want[id] = nil; snap_at, snap_id = frame + PAGE_SNAP, id end
    end
  else
    page_at, last_p, last_t, last_b = nil, "", "", ""
  end
  if snap_at == frame then
    manager.machine.video:snapshot()
    out:write(string.format("S %d %d\n", frame, snap_id))
    snap_at = nil
  end
  out:flush()
end)
