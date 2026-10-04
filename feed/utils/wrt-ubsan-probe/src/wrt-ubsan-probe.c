// SPDX-License-Identifier: GPL-2.0-only
/*
 * wrt-ubsan-probe: overflow a signed integer on purpose (toolchain-o3 D5).
 *
 * The addend comes from the command line (1 without one), so the compiler
 * cannot fold the overflow away. Built with -fsanitize=undefined
 * -fsanitize-trap=undefined, the addition traps (brk #0x3e8 on arm64) and the
 * kernel kills the process with SIGTRAP. Built without, it prints the sum.
 */
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[])
{
	int addend = argc > 1 ? (int)strtol(argv[1], NULL, 10) : 1;
	int sum = INT_MAX;

	sum += addend;
	printf("%d\n", sum);
	return 0;
}
