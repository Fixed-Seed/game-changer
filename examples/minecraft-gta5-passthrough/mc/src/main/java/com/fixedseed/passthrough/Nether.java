package com.fixedseed.passthrough;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.FluidTags;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.NetherPortalBlock;
import net.minecraft.world.level.block.state.BlockState;

/**
 * The Nether comes to the host's world: walking through a lit nether portal (while a host is attached) turns the
 * ground around it into the Nether, bit by bit (netherrack, magma, crimson nylium, soul sand, fire, lava rivers
 * running out of the portal front and back), and Nether mobs keep coming out of it. The host is told when it opens
 * ("nether") so it can turn its own world to hell, and where Minecraft's hot blocks are ("hot") so its people and
 * cars catch fire there. Stopped (and everything put back) with "netheroff". Server thread only.
 */
public final class Nether {
	private static final int RADIUS = 26;
	private static final int SPREAD_TICKS = 200;
	private static final int MAX_FIGHTERS = 30;
	private static final int FLAGS = Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE;

	private static BlockPos pendingPortal;
	private static boolean active;
	private static boolean playerInPortal;
	private static int ticks;
	/** Portal interior: bottom row y, extent along the plane, and the plane's axis (X: spans x, faces ±z). */
	private static int bottomY, topY, minA, maxA, planeC;
	private static Direction.Axis axis = Direction.Axis.X;
	private static double centerX, centerZ;
	/** Every block the Nether changed, with what was there before (put back on stop). */
	private static final Map<BlockPos, BlockState> changed = new LinkedHashMap<>();
	private static final List<int[]> columns = new ArrayList<>(); // {x, z, order key * 1000}
	private static int nextColumn;
	private static final Set<Long> lava = new HashSet<>();
	/** Minecraft's hot blocks the host knows about, and what changed this tick. */
	private static final Map<BlockPos, String> hot = new HashMap<>();
	private static final Map<BlockPos, String> hotAdded = new LinkedHashMap<>();
	private static final Set<BlockPos> hotCleared = new HashSet<>();
	private static final RandomSource random = RandomSource.create();

	private Nether() {
	}

	private static long key(final int x, final int z) {
		return ((long) x << 32) ^ (z & 0xFFFFFFFFL);
	}

	/** Every overworld block change while a host is attached (server thread): portals opening, hot blocks. */
	static void onBlockChanged(final BlockPos pos, final BlockState state) {
		String kind = hotKind(state);
		if (kind != null) {
			if (!kind.equals(hot.get(pos))) {
				BlockPos p = pos.immutable();
				hot.put(p, kind);
				hotAdded.put(p, kind);
				hotCleared.remove(p);
			}
		} else if (hot.remove(pos) != null) {
			BlockPos p = pos.immutable();
			hotAdded.remove(p);
			hotCleared.add(p);
		}

	}

	private static String hotKind(final BlockState state) {
		if (state.is(Blocks.FIRE)) {
			return "fire";
		} else if (state.is(Blocks.SOUL_FIRE)) {
			return "soul";
		} else if (state.is(Blocks.MAGMA_BLOCK) || state.getFluidState().is(FluidTags.LAVA)) {
			return "lava";
		}

		return null;
	}

	static void tick(final MinecraftServer s) {
		ServerLevel level = s.overworld();
		// the player walking into a portal: the host warps the picture while they're in it; the first time, it opens
		ServerPlayer player = s.getPlayerList().getPlayers().isEmpty() ? null : s.getPlayerList().getPlayers().get(0);
		if (player != null && player.level() == level) {
			BlockPos feet = player.blockPosition();
			BlockPos in = level.getBlockState(feet).is(Blocks.NETHER_PORTAL) ? feet
				: level.getBlockState(feet.above()).is(Blocks.NETHER_PORTAL) ? feet.above() : null;
			if ((in != null) != playerInPortal) {
				playerInPortal = in != null;
				Passthrough.events.accept("{\"t\":\"inportal\",\"on\":" + playerInPortal + "}");
			}

			if (in != null && !active && pendingPortal == null) {
				pendingPortal = in;
			}
		}

		if (pendingPortal != null) {
			BlockPos p = pendingPortal;
			pendingPortal = null;
			if (level.getBlockState(p).is(Blocks.NETHER_PORTAL)) {
				start(level, p);
			}
		}

		if (active) {
			ticks++;
			spread(level);
			waves(level);
			if (ticks % 20 == 0 && ticks <= 120) {
				// Minecraft's night falls with the host's (its sky isn't drawn, but its light is)
				WorldBridge.command("time set " + (12000 + ticks * 50));
			}
		}

		flushHot();
	}

	private static void start(final ServerLevel level, final BlockPos seed) {
		// the portal's interior: every connected portal block
		ArrayDeque<BlockPos> todo = new ArrayDeque<>(List.of(seed));
		Set<BlockPos> seen = new HashSet<>();
		axis = level.getBlockState(seed).getValue(NetherPortalBlock.AXIS);
		int minX = seed.getX(), maxX = seed.getX(), minY = seed.getY(), maxY = seed.getY(), minZ = seed.getZ(), maxZ = seed.getZ();
		while (!todo.isEmpty() && seen.size() < 128) {
			BlockPos p = todo.poll();
			if (!seen.add(p) || !level.getBlockState(p).is(Blocks.NETHER_PORTAL)) {
				continue;
			}

			minX = Math.min(minX, p.getX());
			maxX = Math.max(maxX, p.getX());
			minY = Math.min(minY, p.getY());
			maxY = Math.max(maxY, p.getY());
			minZ = Math.min(minZ, p.getZ());
			maxZ = Math.max(maxZ, p.getZ());
			for (Direction d : Direction.values()) {
				todo.add(p.relative(d));
			}
		}

		bottomY = minY;
		topY = maxY;
		minA = axis == Direction.Axis.X ? minX : minZ;
		maxA = axis == Direction.Axis.X ? maxX : maxZ;
		planeC = axis == Direction.Axis.X ? minZ : minX;
		centerX = (minX + maxX + 1) / 2.0;
		centerZ = (minZ + maxZ + 1) / 2.0;
		active = true;
		ticks = 0;
		planSpread();
		Passthrough.LOG.info("nether: portal at {} {} {} axis {}", centerX, bottomY, centerZ, axis);
		// the normal: the way the portal faces (rivers and mobs come out along it)
		double nx = axis == Direction.Axis.X ? 0.0 : 1.0, nz = axis == Direction.Axis.X ? 1.0 : 0.0;
		Passthrough.events.accept(String.format(Locale.ROOT, "{\"t\":\"nether\",\"on\":true,\"pos\":[%.2f,%d,%.2f],\"normal\":[%.0f,%.0f]}",
			centerX, bottomY, centerZ, nx, nz));
	}

	/** Which columns turn, in which order (a ragged circle growing out of the portal), and where lava runs. */
	private static void planSpread() {
		columns.clear();
		lava.clear();
		nextColumn = 0;
		int cx = (int) Math.floor(centerX), cz = (int) Math.floor(centerZ);
		for (int dx = -RADIUS; dx <= RADIUS; dx++) {
			for (int dz = -RADIUS; dz <= RADIUS; dz++) {
				double d = Math.sqrt(dx * dx + dz * dz);
				double ragged = d + 4.0 * noise(cx + dx, cz + dz);
				if (ragged <= RADIUS) {
					columns.add(new int[] {cx + dx, cz + dz, (int) (ragged * 1000)});
				}
			}
		}

		columns.sort((a, b) -> Integer.compare(a[2], b[2]));
		// two rivers out of the portal's front and back, meandering, and a couple of side branches
		double nx = axis == Direction.Axis.X ? 0.0 : 1.0, nz = axis == Direction.Axis.X ? 1.0 : 0.0;
		for (int side = -1; side <= 1; side += 2) {
			river(centerX + nx * side * 2.0, centerZ + nz * side * 2.0, nx * side, nz * side, RADIUS - 2, 2);
		}

		for (int b = 0; b < 3; b++) {
			double t = 5 + random.nextInt(10);
			int side = random.nextBoolean() ? 1 : -1;
			double bx = centerX + nx * side * t, bz = centerZ + nz * side * t;
			double sx = nz * (random.nextBoolean() ? 1 : -1), sz = nx * (random.nextBoolean() ? 1 : -1);
			river(bx, bz, (nx * side + sx) * 0.7071, (nz * side + sz) * 0.7071, 6 + random.nextInt(6), 1);
		}
	}

	private static void river(double x, double z, final double dirX, final double dirZ, final int length, final int width) {
		double drift = 0.0;
		for (int i = 0; i < length; i++) {
			drift = Math.max(-0.8, Math.min(0.8, drift + (random.nextDouble() - 0.5) * 0.7));
			x += dirX + (-dirZ) * drift * 0.5;
			z += dirZ + dirX * drift * 0.5;
			int w = width + (random.nextInt(4) == 0 ? 1 : 0);
			for (int k = 0; k < w; k++) {
				lava.add(key((int) Math.floor(x + (-dirZ) * k), (int) Math.floor(z + dirX * k)));
			}
		}
	}

	/** Smooth-ish value noise in [0, 1) (blobs of a few blocks). */
	private static double noise(final int x, final int z) {
		double fx = x / 5.0, fz = z / 5.0;
		int ix = (int) Math.floor(fx), iz = (int) Math.floor(fz);
		double tx = fx - ix, tz = fz - iz;
		double a = hash(ix, iz), b = hash(ix + 1, iz), c = hash(ix, iz + 1), d = hash(ix + 1, iz + 1);
		double top = a + (b - a) * tx, bottom = c + (d - c) * tx;
		return top + (bottom - top) * tz;
	}

	private static double hash(final int x, final int z) {
		long h = x * 0x9E3779B97F4A7C15L ^ z * 0xC2B2AE3D27D4EB4FL;
		h ^= h >>> 31;
		h *= 0xBF58476D1CE4E5B9L;
		h ^= h >>> 29;
		return (h >>> 11) * 0x1.0p-53;
	}

	/** This tick's share of the spread: the columns the growing circle has reached. */
	private static void spread(final ServerLevel level) {
		if (nextColumn >= columns.size()) {
			return;
		}

		double reach = RADIUS * Math.min(1.0, ticks / (double) SPREAD_TICKS) + 1.5;
		WorldBridge.quietGround(true);
		try {
			while (nextColumn < columns.size() && columns.get(nextColumn)[2] <= reach * 1000) {
				int[] c = columns.get(nextColumn++);
				turn(level, c[0], c[1]);
			}
		} finally {
			WorldBridge.quietGround(false);
		}
	}

	/** One column of the host's ground (its top barrier, near the portal's height) turns to the Nether. */
	private static void turn(final ServerLevel level, final int x, final int z) {
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		int top = Integer.MIN_VALUE;
		for (int y = bottomY + 5; y >= bottomY - 12; y--) {
			p.set(x, y, z);
			if (level.getBlockState(p).is(Blocks.BARRIER) && level.getBlockState(p.above()).isAir()) {
				top = y;
				break;
			}
		}

		if (top == Integer.MIN_VALUE) {
			return; // no host ground here (or something of the player's on it)
		}

		BlockPos ground = new BlockPos(x, top, z);
		BlockPos above = ground.above();
		double n = noise(x * 3 + 17, z * 3 - 5);
		double r = random.nextDouble();
		if (lava.contains(key(x, z))) {
			set(level, ground, Blocks.LAVA.defaultBlockState());
		} else if (n > 0.9) {
			set(level, ground, Blocks.SOUL_SAND.defaultBlockState());
			if (r < 0.08) {
				set(level, above, Blocks.SOUL_FIRE.defaultBlockState());
			}
		} else if (n < 0.22) {
			set(level, ground, Blocks.CRIMSON_NYLIUM.defaultBlockState());
			if (r < 0.18) {
				set(level, above, Blocks.CRIMSON_ROOTS.defaultBlockState());
			} else if (r < 0.24) {
				set(level, above, Blocks.CRIMSON_FUNGUS.defaultBlockState());
			}
		} else if (r < 0.07) {
			set(level, ground, Blocks.MAGMA_BLOCK.defaultBlockState());
		} else {
			set(level, ground, Blocks.NETHERRACK.defaultBlockState());
			if (r < 0.09) {
				set(level, above, Blocks.FIRE.defaultBlockState());
			} else if (r < 0.095) {
				// the odd basalt pillar (solid: the host gets these as collision too)
				int h = 2 + random.nextInt(3);
				WorldBridge.quietGround(false);
				for (int k = 0; k < h; k++) {
					set(level, above.above(k), Blocks.BASALT.defaultBlockState());
				}

				WorldBridge.quietGround(true);
			}
		}
	}

	private static void set(final ServerLevel level, final BlockPos pos, final BlockState state) {
		BlockPos p = pos.immutable();
		changed.putIfAbsent(p, level.getBlockState(p));
		level.setBlock(p, state, FLAGS);
		onBlockChanged(p, state); // quiet ground skips the usual report; hot blocks still count
	}

	/** Nether mobs keep coming out of the portal (both sides), a few at a time. */
	private static void waves(final ServerLevel level) {
		if (ticks > 20 * 60 * 5) {
			return;
		}

		switch (ticks) {
			case 30 -> spawn(level, "zombified_piglin", 3);
			case 70 -> spawn(level, "ghast", 1);
			case 110 -> spawn(level, "wither_skeleton", 2);
			case 160 -> spawn(level, "blaze", 2);
			case 220 -> {
				spawn(level, "zombified_piglin", 3);
				spawn(level, "magma_cube", 2);
			}
			default -> {
				if (ticks > 220 && ticks % 200 == 0) {
					if (ticks % 400 == 0) {
						spawn(level, "zombified_piglin", 2);
						spawn(level, "wither_skeleton", 1);
						spawn(level, "blaze", 1);
					} else {
						spawn(level, "magma_cube", 2);
						spawn(level, "zombified_piglin", 2);
					}
				}

				if (ticks % 900 == 0) {
					spawn(level, "ghast", 1);
				}
			}
		}
	}

	private static void spawn(final ServerLevel level, final String kind, final int count) {
		Optional<EntityType<?>> type = BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.withDefaultNamespace(kind));
		if (type.isEmpty()) {
			return;
		}

		int fighters = 0;
		for (Entity e : level.getAllEntities()) {
			if (e instanceof Mob && e instanceof net.minecraft.world.entity.monster.Enemy && e.isAlive()
				&& e.distanceToSqr(centerX, bottomY, centerZ) < 96 * 96) {
				fighters++;
			}
		}

		for (int i = 0; i < count && fighters < MAX_FIGHTERS; i++) {
			int a = minA + random.nextInt(maxA - minA + 1);
			int side = random.nextBoolean() ? 1 : -1;
			BlockPos at;
			switch (kind) {
				case "ghast" -> at = along(a, topY + 4, side * 5); // big: well clear of the frame
				case "blaze" -> at = along(a, bottomY + 1, side * 2);
				case "magma_cube" -> at = along(a, bottomY, side * 2);
				default -> at = along(a, bottomY, 0); // in the portal itself: they walk out of it
			}

			Entity e = type.get().spawn(level, at, EntitySpawnReason.COMMAND);
			if (e instanceof Mob mob) {
				mob.setPersistenceRequired();
				fighters++;
			}
		}
	}

	/** A block position: `a` along the portal's plane, height y, `out` blocks out of it (either side). */
	private static BlockPos along(final int a, final int y, final int out) {
		return axis == Direction.Axis.X ? new BlockPos(a, y, planeC + out) : new BlockPos(planeC + out, y, a);
	}

	private static void flushHot() {
		if (!Passthrough.active || (hotAdded.isEmpty() && hotCleared.isEmpty())) {
			return;
		}

		StringBuilder lavaB = new StringBuilder(), fireB = new StringBuilder(), soulB = new StringBuilder(), clearB = new StringBuilder();
		for (Map.Entry<BlockPos, String> e : hotAdded.entrySet()) {
			StringBuilder b = switch (e.getValue()) {
				case "fire" -> fireB;
				case "soul" -> soulB;
				default -> lavaB;
			};
			append(b, e.getKey());
		}

		for (BlockPos p : hotCleared) {
			append(clearB, p);
		}

		hotAdded.clear();
		hotCleared.clear();
		Passthrough.events.accept("{\"t\":\"hot\",\"lava\":[" + lavaB + "],\"fire\":[" + fireB + "],\"soul\":[" + soulB + "],\"clear\":[" + clearB + "]}");
	}

	private static void append(final StringBuilder b, final BlockPos p) {
		b.append(b.isEmpty() ? "" : ",").append(p.getX()).append(',').append(p.getY()).append(',').append(p.getZ());
	}

	/** Build a nether portal frame on the ground at (x, z) near height y, facing `yaw`, and light it (for scripted shots). */
	public static void buildPortal(final double x, final double y, final double z, final float yaw) {
		MinecraftServer s = WorldBridge.server();
		if (s == null) {
			return;
		}

		s.execute(() -> {
			ServerLevel level = s.overworld();
			int bx = (int) Math.floor(x), bz = (int) Math.floor(z);
			BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
			int ground = Integer.MIN_VALUE;
			for (int yy = (int) Math.floor(y) + 4; yy >= (int) Math.floor(y) - 8; yy--) {
				p.set(bx, yy, bz);
				if (!level.getBlockState(p).isAir() && level.getBlockState(p.above()).isAir()) {
					ground = yy;
					break;
				}
			}

			if (ground == Integer.MIN_VALUE) {
				Passthrough.LOG.warn("portal: no ground at {} {}", bx, bz);
				return;
			}

			// facing along x (yaw ~90/270): the plane spans z; facing along z: the plane spans x
			double rad = Math.toRadians(yaw);
			boolean spansZ = Math.abs(Math.sin(rad)) > Math.abs(Math.cos(rad));
			int y0 = ground + 1;
			for (int a = -1; a <= 2; a++) {
				for (int h = 0; h <= 4; h++) {
					BlockPos at = spansZ ? new BlockPos(bx, y0 + h, bz + a) : new BlockPos(bx + a, y0 + h, bz);
					boolean frame = a == -1 || a == 2 || h == 0 || h == 4;
					changed.putIfAbsent(at, level.getBlockState(at));
					level.setBlock(at, frame ? Blocks.OBSIDIAN.defaultBlockState() : Blocks.AIR.defaultBlockState(), Block.UPDATE_ALL);
				}
			}

			BlockPos inside = spansZ ? new BlockPos(bx, y0 + 1, bz) : new BlockPos(bx, y0 + 1, bz);
			level.setBlock(inside, Blocks.FIRE.defaultBlockState(), Block.UPDATE_ALL); // lights it (a valid frame)
		});
	}

	/** Close the Nether: everything it changed goes back, its mobs and fires go, the night lifts. */
	public static void stop() {
		MinecraftServer s = WorldBridge.server();
		if (s != null) {
			s.execute(() -> close(s.overworld()));
		}
	}

	/** Server thread. Also when the server stops (before the world is saved), so nothing of it is left in the save. */
	private static void close(final ServerLevel level) {
		{
			// reported as usual (not quiet): the host drops its collision for the basalt pillars
			List<BlockPos> order = new ArrayList<>(changed.keySet());
			// top-down, so nothing gets a chance to drop or flow
			order.sort((a, b) -> Integer.compare(b.getY(), a.getY()));
			for (BlockPos p : order) {
				level.setBlock(p, changed.get(p), FLAGS);
				onBlockChanged(p, changed.get(p));
			}

			for (BlockPos p : new ArrayList<>(hot.keySet())) {
				if (hotKind(level.getBlockState(p)) != null) {
					level.setBlock(p, Blocks.AIR.defaultBlockState(), FLAGS);
				}

				onBlockChanged(p, Blocks.AIR.defaultBlockState());
			}

			// close the portal (the frame stays): lighting it again opens the Nether again
			if (active) {
				for (int a = minA; a <= maxA; a++) {
					for (int y = bottomY; y <= topY; y++) {
						BlockPos p = along(a, y, 0);
						if (level.getBlockState(p).is(Blocks.NETHER_PORTAL)) {
							level.setBlock(p, Blocks.AIR.defaultBlockState(), FLAGS);
						}
					}
				}
			}

			boolean wasOpen = active || !changed.isEmpty();
			changed.clear();
			columns.clear();
			active = false;
			pendingPortal = null;
			MobWar.discardFighters(level);
			if (wasOpen) {
				WorldBridge.command("time set noon");
			}

			Passthrough.events.accept("{\"t\":\"nether\",\"on\":false}");
			Passthrough.LOG.info("nether: closed");
		}
	}

	static boolean active() {
		return active;
	}

	/** A block of the host's ground the Nether turned (netherrack, lava, ...: not something to collide with). */
	static boolean isGround(final BlockPos pos) {
		BlockState before = changed.get(pos);
		return before != null && before.is(Blocks.BARRIER);
	}

	/** The host (re)connected: tell it again that the Nether is open, and where every hot block is. */
	public static void resync() {
		MinecraftServer s = WorldBridge.server();
		if (s == null) {
			return;
		}

		s.execute(() -> {
			if (active) {
				double nx = axis == Direction.Axis.X ? 0.0 : 1.0, nz = axis == Direction.Axis.X ? 1.0 : 0.0;
				Passthrough.events.accept(String.format(Locale.ROOT, "{\"t\":\"nether\",\"on\":true,\"pos\":[%.2f,%d,%.2f],\"normal\":[%.0f,%.0f]}",
					centerX, bottomY, centerZ, nx, nz));
			}

			hotAdded.putAll(hot);
		});
	}

	static void detach(final MinecraftServer s) {
		if (active || !changed.isEmpty()) {
			close(s.overworld());
		}

		active = false;
		pendingPortal = null;
		changed.clear();
		columns.clear();
		hot.clear();
		hotAdded.clear();
		hotCleared.clear();
	}
}
