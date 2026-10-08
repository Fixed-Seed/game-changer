package com.fixedseed.passthrough.client.mixin;

import net.minecraft.client.KeyMapping;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(KeyMapping.class)
public interface KeyMappingAccessor {
	@Accessor("clickCount")
	int passthrough$getClickCount();

	@Accessor("clickCount")
	void passthrough$setClickCount(int clickCount);
}
