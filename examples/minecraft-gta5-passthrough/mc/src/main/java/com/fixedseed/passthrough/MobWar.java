package com.fixedseed.passthrough;

import com.fixedseed.passthrough.mixin.MobAccessor;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicReference;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.DamageTypeTags;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.ai.attributes.AttributeInstance;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.ai.goal.GoalSelector;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.projectile.Projectile;

/**
 * Minecraft's mobs vs the host's people. The host lists its people ("peds"); each gets an invisible, AI-less
 * villager "proxy" here that follows it and that hostile mobs hunt. A mob's hit on a proxy goes back to the host
 * ("mobhit"), which hurts the real person. The other way round, the host keeps a stand-in for every mob ("mobs") that
 * its police shoot at, and sends the damage back ("mobdmg").
 */
public final class MobWar {
	public static final String PROXY_TAG = "gta_proxy";
	/** Mobs hunt proxies this far away (blocks). */
	private static final double FOLLOW_RANGE = 48.0;
	/** Host people further than this from the player aren't mirrored, nor mobs reported (blocks). */
	private static final double REPORT_RANGE = 96.0;

	/** The newest "peds" list from the host, flattened [handle, x, y, z, ...] (WebSocket thread -> server tick). */
	private static final AtomicReference<double[]> peds = new AtomicReference<>();
	private static volatile long pedsNanos;
	/** Host damage to mobs, [entity id, amount] (WebSocket thread -> server tick). */
	private static final ConcurrentLinkedQueue<double[]> damage = new ConcurrentLinkedQueue<>();

	// server thread only
	private static final Map<Integer, Villager> proxies = new HashMap<>();
	private static final Map<Integer, Integer> handleOf = new HashMap<>();
	private static final Map<Integer, Integer> missingTicks = new HashMap<>();
	private static boolean reportedMobs;

	private MobWar() {
	}

	/** Brain-driven hostiles: they pick targets from brain memories, not goals, so they'd never join the fight. */
	private static final java.util.Set<String> BRAIN_MOBS = java.util.Set.of("piglin", "piglin_brute", "hoglin", "zoglin", "breeze", "creaking", "warden");

	/**
	 * A host person's stand-in. The server knows its tag; the client only sees that it's an invisible villager (a
	 * permanent hidden invisibility effect keeps that flag set: Minecraft resets it on sync otherwise).
	 */
	public static boolean isProxy(final Entity e) {
		return e instanceof Villager && (e.isInvisible() || e.entityTags().contains(PROXY_TAG));
	}

	/** Mobs that join the fight: hostile, goal-driven ones. */
	private static boolean fighter(final Entity e) {
		return e instanceof Mob && e instanceof Enemy && !isProxy(e) && !BRAIN_MOBS.contains(BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).getPath());
	}

	public static void peds(final double[] flat) {
		peds.set(flat);
		pedsNanos = System.nanoTime();
	}

	public static void damage(final int id, final double amount) {
		damage.add(new double[] {id, amount});
	}

	/** New mobs (and mobs loaded again) hunt proxies; stale proxies from an earlier session are removed. */
	static void onEntityLoad(final Entity e, final ServerLevel level) {
		if (e instanceof Villager v && v.entityTags().contains(PROXY_TAG) && !proxies.containsValue(v)) {
			v.discard();
			return;
		}

		if (!fighter(e)) {
			return;
		}

		Mob mob = (Mob) e;
		GoalSelector targets = ((MobAccessor) mob).passthrough$targetSelector();
		if (targets.getAvailableGoals().stream().noneMatch(w -> w.getGoal() instanceof ProxyTargetGoal)) {
			targets.addGoal(2, new ProxyTargetGoal(mob));
		}

		AttributeInstance range = mob.getAttribute(Attributes.FOLLOW_RANGE);
		if (range != null && range.getBaseValue() < FOLLOW_RANGE) {
			range.setBaseValue(FOLLOW_RANGE);
		}
	}

	/** A proxy was hurt (server thread, from LivingEntity.hurtServer; the damage itself is always cancelled). */
	public static void onProxyHit(final LivingEntity proxy, final DamageSource source, final float amount) {
		Integer handle = handleOf.get(proxy.getId());
		Entity attacker = source.getEntity();
		if (source.getDirectEntity() instanceof Projectile projectile && !(attacker instanceof Player)) {
			projectile.discard(); // a skeleton's arrow ends in the person it hit
		}

		// explosions are the host's own already (every Minecraft explosion is mirrored); Steve's hits are handled there too
		if (handle == null || attacker == null || attacker instanceof Player || source.is(DamageTypeTags.IS_EXPLOSION)) {
			return;
		}

		String kind = BuiltInRegistries.ENTITY_TYPE.getKey(attacker.getType()).getPath();
		Passthrough.events.accept(String.format(Locale.ROOT, "{\"t\":\"mobhit\",\"h\":%d,\"d\":%.2f,\"from\":[%.3f,%.3f,%.3f],\"k\":\"%s\"}",
			handle, amount, attacker.getX(), attacker.getY(), attacker.getZ(), kind));
	}

	/** Every server tick (server thread). */
	static void tick(final MinecraftServer s) {
		ServerLevel level = s.overworld();
		syncProxies(level);
		applyDamage(level);
		if (Passthrough.active) {
			reportMobs(s, level);
		}
	}

	private static void syncProxies(final ServerLevel level) {
		if (!proxies.isEmpty() && System.nanoTime() - pedsNanos > 1_500_000_000L) {
			clearProxies(); // the host stopped sending: nobody to hunt
			return;
		}

		double[] p = peds.getAndSet(null);
		if (p == null) {
			return;
		}

		Map<Integer, Boolean> seen = new HashMap<>();
		for (int i = 0; i + 3 < p.length; i += 4) {
			int handle = (int) p[i];
			double x = p[i + 1], y = p[i + 2], z = p[i + 3];
			seen.put(handle, true);
			Villager v = proxies.get(handle);
			if (v == null || v.isRemoved()) {
				v = EntityTypes.VILLAGER.create(level, EntitySpawnReason.COMMAND);
				if (v == null) {
					continue;
				}

				v.setInvisible(true);
				v.addEffect(new MobEffectInstance(MobEffects.INVISIBILITY, MobEffectInstance.INFINITE_DURATION, 0, false, false), null);
				v.setNoAi(true);
				v.setNoGravity(true);
				v.setSilent(true);
				v.addTag(PROXY_TAG);
				v.snapTo(x, y, z, 0.0F, 0.0F);
				proxies.put(handle, v); // before adding: the load event must not take it for a stale one
				if (!level.addFreshEntity(v)) {
					proxies.remove(handle);
					continue;
				}

				handleOf.put(v.getId(), handle);
			} else {
				v.setPos(x, y, z);
			}

			missingTicks.remove(handle);
		}

		// hysteresis: a person missing from a few lists in a row (out of range, dead, despawned) loses their proxy
		for (Iterator<Map.Entry<Integer, Villager>> it = proxies.entrySet().iterator(); it.hasNext();) {
			Map.Entry<Integer, Villager> e = it.next();
			if (seen.containsKey(e.getKey())) {
				continue;
			}

			int missing = missingTicks.merge(e.getKey(), 1, Integer::sum);
			if (missing > 6 || e.getValue().isRemoved()) {
				handleOf.remove(e.getValue().getId());
				e.getValue().discard();
				missingTicks.remove(e.getKey());
				it.remove();
			}
		}
	}

	private static void applyDamage(final ServerLevel level) {
		for (double[] d; (d = damage.poll()) != null;) {
			if (!(level.getEntity((int) d[0]) instanceof Mob mob) || !mob.isAlive()) {
				continue;
			}

			// from the nearest person (a cop, most likely), so the mob turns on them
			LivingEntity from = nearestProxy(level, mob);
			DamageSource source = from != null ? level.damageSources().mobAttack(from) : level.damageSources().generic();
			mob.damageCooldownTime = 0; // automatic fire lands several hits inside the usual 10-tick cooldown
			mob.hurtServer(level, source, (float) d[1]);
		}
	}

	private static LivingEntity nearestProxy(final ServerLevel level, final Mob mob) {
		LivingEntity best = null;
		double bestD = 48.0 * 48.0;
		for (Villager v : proxies.values()) {
			double dd = v.distanceToSqr(mob);
			if (!v.isRemoved() && dd < bestD) {
				best = v;
				bestD = dd;
			}
		}

		return best;
	}

	/** {"t":"mobs","m":[[id,"zombie",x,y,z],...]}: every fighting mob near the player, every tick while there are any. */
	private static void reportMobs(final MinecraftServer s, final ServerLevel level) {
		ServerPlayer player = s.getPlayerList().getPlayers().isEmpty() ? null : s.getPlayerList().getPlayers().get(0);
		if (player == null) {
			return;
		}

		List<Entity> near = level.getEntities((Entity) null, player.getBoundingBox().inflate(REPORT_RANGE), MobWar::fighter);
		if (near.isEmpty() && !reportedMobs) {
			return;
		}

		StringBuilder b = new StringBuilder("{\"t\":\"mobs\",\"m\":[");
		int n = 0;
		for (Entity e : near) {
			if (!e.isAlive()) {
				continue;
			}

			b.append(n++ == 0 ? "" : ",").append(String.format(Locale.ROOT, "[%d,\"%s\",%.3f,%.3f,%.3f]",
				e.getId(), BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).getPath(), e.getX(), e.getY(), e.getZ()));
		}

		Passthrough.events.accept(b.append("]}").toString());
		reportedMobs = n > 0;
	}

	/**
	 * Spawn `count` mobs of `kind` (e.g. "zombie") on the ground `minR`..`maxR` blocks from the player, within `arc`
	 * degrees either side of where the player faces (or of `yawOffset` from it); or, given `at` ({x, y, z}: a fixed
	 * spot, y near its ground), all round that spot instead, wherever the player is.
	 */
	public static void spawn(final String kind, final int count, final double minR, final double maxR, final double arc, final double yawOffset,
		final double[] at) {
		MinecraftServer s = serverOrNull();
		if (s == null) {
			return;
		}

		s.execute(() -> {
			ServerLevel level = s.overworld();
			ServerPlayer player = s.getPlayerList().getPlayers().isEmpty() ? null : s.getPlayerList().getPlayers().get(0);
			Optional<EntityType<?>> type = BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.withDefaultNamespace(kind));
			if (player == null || type.isEmpty()) {
				Passthrough.LOG.warn("spawnmobs: no player or unknown mob {}", kind);
				return;
			}

			ThreadLocalRandom random = ThreadLocalRandom.current();
			double cx = at != null ? at[0] : player.getX(), cy = at != null ? at[1] : player.getY(), cz = at != null ? at[2] : player.getZ();
			double baseYaw = at != null ? 0.0 : player.getYRot() + yawOffset, spread = at != null ? 180.0 : arc;
			int spawned = 0;
			for (int i = 0; i < count * 4 && spawned < count; i++) {
				double yaw = Math.toRadians(baseYaw + (random.nextDouble() * 2.0 - 1.0) * spread);
				double r = minR + random.nextDouble() * (maxR - minR);
				int x = (int) Math.floor(cx - Math.sin(yaw) * r), z = (int) Math.floor(cz + Math.cos(yaw) * r);
				BlockPos ground = groundAt(level, x, (int) Math.floor(cy), z);
				if (ground == null) {
					continue; // no host ground there (yet)
				}

				Entity e = type.get().spawn(level, ground, EntitySpawnReason.COMMAND);
				if (e instanceof Mob mob) {
					mob.setPersistenceRequired();
					spawned++;
				}
			}

			Passthrough.LOG.info("spawnmobs: {} x {}", spawned, kind);
		});
	}

	/** The free block above the host's ground near height y in column (x, z), or null. */
	private static BlockPos groundAt(final ServerLevel level, final int x, final int y, final int z) {
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		for (int dy = 6; dy >= -12; dy--) {
			p.set(x, y + dy, z);
			if (!level.getBlockState(p).isAir() && level.getBlockState(p.above()).isAir() && level.getBlockState(p.above(2)).isAir()) {
				return p.above().immutable();
			}
		}

		return null;
	}

	/** Remove every fighting mob (not the player's other things). */
	public static void clearMobs() {
		MinecraftServer s = serverOrNull();
		if (s != null) {
			s.execute(() -> discardFighters(s.overworld()));
		}
	}

	/** Server thread. */
	static void discardFighters(final ServerLevel level) {
		List<Entity> all = new ArrayList<>();
		level.getAllEntities().forEach(all::add);
		all.stream().filter(e -> fighter(e) || isProxy(e)).forEach(Entity::discard);
	}

	/** The host went away: nobody left to hunt. */
	public static void hostGone() {
		MinecraftServer s = serverOrNull();
		if (s != null) {
			s.execute(MobWar::clearProxies);
		}
	}

	private static void clearProxies() {
		proxies.values().forEach(Entity::discard);
		proxies.clear();
		handleOf.clear();
		missingTicks.clear();
	}

	static void detach(final MinecraftServer s) {
		// the world is saved next: none of the fight is kept in it
		discardFighters(s.overworld());
		proxies.clear();
		handleOf.clear();
		missingTicks.clear();
		peds.set(null);
		damage.clear();
		reportedMobs = false;
	}

	private static MinecraftServer serverOrNull() {
		return WorldBridge.server();
	}
}
