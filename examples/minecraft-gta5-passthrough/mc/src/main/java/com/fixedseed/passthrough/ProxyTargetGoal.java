package com.fixedseed.passthrough;

import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.ai.goal.target.NearestAttackableTargetGoal;
import net.minecraft.world.entity.npc.villager.Villager;

/** Hunt the nearest host person's proxy: invisible, and often behind host walls Minecraft can't see, so neither counts. */
final class ProxyTargetGoal extends NearestAttackableTargetGoal<Villager> {
	ProxyTargetGoal(final Mob mob) {
		super(mob, Villager.class, 10, false, false, (target, level) -> MobWar.isProxy(target));
		this.targetConditions.ignoreInvisibilityTesting().ignoreLineOfSight();
	}
}
