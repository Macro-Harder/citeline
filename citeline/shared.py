"""Helpers shared across the package's modules.

Each function here stands in one place: the modules that
use it import it from here, so a correction lands once
and every reader sees the same reading. This module
imports nothing from the package but the error
vocabulary, so no import cycle can run through it.
"""

import os
from bisect import bisect_left, bisect_right

from citeline import errors


def _get(record, name, default=None):
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)

def _fail(token, message):
    raise errors.CitelineError(message, token=token)

def _flush_directory(directory):
    """Flush one directory to storage, the directory
    flush step of the pinned B4 write sequence."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def _host_from_authority(authority):
    host = authority.rsplit("@", 1)[-1]
    if host.startswith("["):
        closing = host.find("]")
        host = host[:closing + 1] if closing >= 0 else host
    else:
        host = host.split(":", 1)[0]
    return host

def _honesty_sentence():
    try:
        from citeline import reporting
        return reporting.HONESTY_SENTENCE
    except (ImportError, AttributeError):
        return (
            "This score is a signal index. It measures the "
            "presence of citability signals. It is not "
            "validated as a predictor of citation, and it "
            "does not verify truth.")

def _similar_components(type_sets):
    """The components of the similarity graph over distinct
    non empty shingle sets, computed exactly.

    Two sets are similar where their shared count stands at
    the 0.80 Jaccard bound, judged in integers as shared
    times 9 standing at least 4 times the sum of the sizes.
    No structure grows with the number of pairs and no subset
    of a set is ever stored: an inverted index over single
    shingles stands in place of both.

    Each component grows from one seed set. The seed pass
    stands in prefix form: the seed shingles stand ordered
    by their posting counts, a set similar to the seed must
    share a shingle of the seed prefix at the rare end of
    that ordering, and the candidates those postings name
    stand judged exactly against the seed, so every set
    similar to the seed joins at once, which settles a
    clique shape in that one pass, at a price set by the
    prefix postings in place of the postings of the whole
    seed. Where the exact judgement of the candidates
    stands priced past a counted reading, the seed pass
    stands in that counted form instead, at any seed size
    and at any prefix posting total: the shared count of
    every unvisited set with the seed stands counted in
    parallel bit planes in batches of the seed shingles
    in their rare first order, the planes standing loaded
    with the allowance its size carries for each set, so
    a set whose counted misses stand past its allowance
    holds a plane value standing below the count of
    shingles counted and stands excluded in full and
    counted no further, the survivor judgement standing
    as one comparison of the planes against the counted
    total for every size together, and the sets standing
    live at the end of the counting stand at exactly the
    sets whose full count reaches the threshold for their
    size, the same exact judgement at a price set by the
    batches the live sets survive and by one allowance
    plane build per distinct seed size.
    The component then grows
    layer by layer from the sets that joined last, the
    frontier. A set can join through a frontier member only
    where it shares a shingle with one, so the candidates of
    a layer are the unvisited sets standing in the postings
    of the distinct frontier shingles, each posting holding
    unvisited sets only. A candidate stands counted against
    each frontier member on that member's own threshold:
    its shared count with the seed plus the part of the
    member standing outside the seed bounds it, and so does
    its shared count with the frontier, counted from the
    light postings with the heavy shingles counted as a
    bound per member, and a member whose size cannot reach
    the bound for the candidate's size stands impossible
    for it. A candidate excluded on every member's own
    threshold stands excluded in bulk for the layer, which
    holds a reject pool sharing one small common part out
    of every layer even where the frontier mixes sizes.
    The candidates the bounds leave open are judged
    exactly, against the frontier members that share one
    of a small picked set of the candidate shingles: a
    similar member misses at most the allowance of the
    candidate shingles that its threshold fixes, so it
    shares at least one of any allowance plus one of them.
    A chain shape, where each layer adds the next link or
    two, therefore costs a small candidate scan per layer
    in place of a scan of the whole component per pass.
    The layer work stands in the first queue, processed
    first and to exhaustion, and a candidate sharing only
    heavy shingles with the frontier, excluded on every
    member's own threshold, passes to a second queue and
    stands judged once against the whole component when
    the first queue stands exhausted, as the body of the
    computation states in full.
    """
    count = len(type_sets)
    # Shingles stand interned to small integers for the
    # whole computation, so the index, the postings, and
    # every count work on integers alone. The postings
    # stand as built, and a posting count per shingle,
    # lowered as sets stand marked, stands in place of a
    # posting rebuilt at every mark: a reader of a posting
    # judges the visited flag of each member it meets.
    shingle_ids = {}
    sets = []
    postings = []
    for index, shingle_set in enumerate(type_sets):
        id_set = set()
        for shingle in shingle_set:
            ident = shingle_ids.get(shingle)
            if ident is None:
                ident = len(shingle_ids)
                shingle_ids[shingle] = ident
                postings.append([])
            id_set.add(ident)
            postings[ident].append(index)
        sets.append(id_set)
    unvisited_count = [len(members) for members in postings]
    visited = [False] * count
    by_size = {}
    for index, id_set in enumerate(sets):
        by_size.setdefault(len(id_set), set()).add(index)
    remaining = count
    components = []
    # One ordering of the shingles for the whole
    # computation, by posting count, rare shingles first.
    # The seed pass reads the rare end of a seed as its
    # prefix, and the ordering stands fixed while it runs,
    # which is all the prefix argument the seed pass states
    # needs. Each set stands sorted once, at the first seed
    # pass that reads it, and the sorted form stands kept.
    shingle_rank = {}
    for rank, ident in enumerate(sorted(
            range(len(postings)),
            key=unvisited_count.__getitem__)):
        shingle_rank[ident] = rank
    ordered_cache = {}
    # Posting bitsets over the set indices, built lazily
    # per shingle the first time the counted seed reading
    # needs one and kept for the computation: bit position
    # index stands for the set of that index, in a byte
    # array read as a little endian integer. The size masks
    # stand built once, and the visited mask stands kept
    # by mark below, so the counted reading names its sets
    # from the masks alone.
    bit_width = (count + 7) // 8
    all_mask = (1 << count) - 1 if count else 0
    bit_postings = {}
    size_masks = {}
    for mask_index, mask_set in enumerate(sets):
        size_masks[len(mask_set)] = size_masks.get(
            len(mask_set), 0) | (1 << mask_index)
    visited_mask = 0
    sorted_sizes = sorted(size_masks)
    size_prefix = [0]
    for sorted_size in sorted_sizes:
        size_prefix.append(size_prefix[-1] | size_masks[sorted_size])

    def bit_posting(ident):
        posting = bit_postings.get(ident)
        if posting is None:
            packed = bytearray(bit_width)
            for other in postings[ident]:
                packed[other >> 3] |= 1 << (other & 7)
            posting = int.from_bytes(packed, "little")
            bit_postings[ident] = posting
        return posting

    allowance_planes_cache = {}

    band_sizes_cache = {}
    band_pointer_cache = {}

    def band_lowest_threshold(seed_size):
        # The lowest threshold standing at a seed size:
        # the threshold of the smallest size in the
        # threshold band of the seed size that still
        # holds an unvisited set, the threshold standing
        # nondecreasing in the size, or None where no
        # band size stands. The band sizes stand built
        # once per distinct seed size as a slice of the
        # sorted distinct sizes, and the pointer over
        # them stands kept per seed size and only
        # advances, a size whose sets all stand visited
        # never standing unvisited again, so the seed
        # pass reads this judgement in a step or two in
        # place of rebuilding the thresholds of every
        # distinct size standing at every seed.
        sizes = band_sizes_cache.get(seed_size)
        if sizes is None:
            band_lo = -(-4 * seed_size // 5)
            band_hi = 5 * seed_size // 4
            sizes = sorted_sizes[
                bisect_left(sorted_sizes, band_lo):
                bisect_right(sorted_sizes, band_hi)]
            band_sizes_cache[seed_size] = sizes
            band_pointer_cache[seed_size] = 0
        pointer = band_pointer_cache[seed_size]
        while pointer < len(sizes) and not by_size[sizes[pointer]]:
            pointer += 1
        band_pointer_cache[seed_size] = pointer
        if pointer == len(sizes):
            return None
        size = sizes[pointer]
        return -(-4 * (seed_size + size) // 9)

    def allowance_planes(seed_size):
        # The bit planes of the allowance of every set at
        # this seed size: plane bit b holds the sets whose
        # size stands in the threshold band of the seed
        # size and whose allowance at that size carries
        # bit b. The allowance of a size stands as the
        # seed size less the threshold for its size, a
        # nonincreasing step function of the size, so the
        # sizes carrying one bit of it stand as a union of
        # size intervals, each interval read from the
        # prefix masks over the sorted distinct sizes in
        # two lookups. The planes stand built once per
        # distinct seed size and kept for the computation,
        # so their price stands at the allowance range of
        # the seed size, never at the product of the batch
        # count and the distinct size count.
        cached = allowance_planes_cache.get(seed_size)
        if cached is not None:
            return cached
        band_lo = -(-4 * seed_size // 5)
        band_hi = 5 * seed_size // 4
        band_mask = size_prefix[bisect_right(sorted_sizes, band_hi)] ^ \
            size_prefix[bisect_left(sorted_sizes, band_lo)]
        top_allowance = seed_size - -(-4 * (seed_size + band_lo) // 9)
        planes = [0] * max(1, top_allowance.bit_length())
        if top_allowance:
            lo_index = bisect_left(sorted_sizes, band_lo)
            hi_index = bisect_right(sorted_sizes, band_hi)
            bit = 0
            while (1 << bit) <= top_allowance:
                width = 1 << bit
                step = width << 1
                plane = 0
                low_a = width
                while low_a <= top_allowance:
                    high_a = low_a + width - 1
                    if high_a > top_allowance:
                        high_a = top_allowance
                    # The sizes whose allowance stands in
                    # [low_a, high_a]: the allowance of a
                    # size stands at least a exactly where
                    # the size stands at most
                    # (5 * seed_size - 9 * a) // 4, and at
                    # most a exactly where the size stands
                    # past (5 * seed_size - 9 * a - 9) // 4.
                    s_high = (5 * seed_size - 9 * low_a) // 4
                    s_low = (5 * seed_size - 9 * high_a - 9) // 4 + 1
                    if s_low < band_lo:
                        s_low = band_lo
                    if s_high > band_hi:
                        s_high = band_hi
                    if s_low <= s_high:
                        first = bisect_left(
                            sorted_sizes, s_low, lo_index, hi_index)
                        last = bisect_right(
                            sorted_sizes, s_high, lo_index, hi_index)
                        if first < last:
                            plane |= size_prefix[last] ^ \
                                size_prefix[first]
                    low_a += step
                planes[bit] = plane
                bit += 1
        cached = (planes, band_mask)
        allowance_planes_cache[seed_size] = cached
        return cached

    def counted_seed_layer():
        # The shared count of every unvisited set with the
        # seed, counted in parallel in batches of the seed
        # shingles in their rare first order: one bit plane
        # per bit of the count, each seed shingle posting
        # added into the planes in turn, the postings
        # standing masked to the sets that stand live after
        # the batch before. The planes stand loaded at the
        # start with the allowance of each set at the seed
        # size, so the value they hold for a set stands at
        # its counted shared count plus its allowance, and
        # a set similar to the seed, whose misses stand at
        # most its allowance, holds a value standing at
        # least the count of shingles counted so far at
        # every point of the counting, while a set standing
        # below that mark at any point can never reach the
        # seed size the value must reach at the end. The
        # survivor judgement therefore stands as one
        # comparison of the planes against the counted
        # total, read in bitwise form once per batch for
        # every size together, in place of one comparison
        # per distinct size per batch, and the sets
        # standing live at the end of the counting stand
        # at exactly the sets whose full count reaches the
        # threshold for their size, the same exact
        # judgement the prefix form makes, so no candidate
        # stands judged set against set on this reading
        # and no set the rule names stands lost.
        planes, band_mask = allowance_planes(seed_size)
        active = band_mask & all_mask & ~visited_mask
        if not active:
            return []
        ordered = ordered_set(seed)
        planes = list(planes)
        counted = 0
        index = 0
        while index < len(ordered):
            batch = ordered[index:index + 128]
            index += len(batch)
            for ident in batch:
                carry = bit_posting(ident) & active
                level = 0
                while carry:
                    if level == len(planes):
                        planes.append(0)
                    next_carry = planes[level] & carry
                    planes[level] ^= carry
                    carry = next_carry
                    level += 1
            counted += len(batch)
            equal = all_mask
            greater = 0
            top = max(len(planes), counted.bit_length())
            for bit in range(top - 1, -1, -1):
                plane = planes[bit] if bit < len(planes) else 0
                if (counted >> bit) & 1:
                    equal &= plane
                else:
                    greater |= equal & plane
                    equal &= all_mask ^ plane
            active = (greater | equal) & active
            if not active:
                return []
            if counted < len(ordered):
                planes = [plane & active for plane in planes]
        layer = []
        mask = active
        while mask:
            lowest = mask & -mask
            layer.append(lowest.bit_length() - 1)
            mask ^= lowest
        return sorted(layer)

    def ordered_set(index):
        ordered = ordered_cache.get(index)
        if ordered is None:
            ordered = sorted(
                sets[index], key=shingle_rank.__getitem__)
            ordered_cache[index] = ordered
        return ordered

    def mark(index):
        nonlocal remaining, visited_mask
        visited[index] = True
        visited_mask |= 1 << index
        remaining -= 1
        by_size[len(sets[index])].discard(index)
        for ident in sets[index]:
            unvisited_count[ident] -= 1

    for seed in range(count):
        if visited[seed]:
            continue
        seed_set = sets[seed]
        seed_size = len(seed_set)
        component = [seed]
        mark(seed)
        # The seed pass in prefix form. A set similar to the
        # seed shares at least the threshold count of the
        # seed shingles for its size, so where the prefix
        # stands longer than the seed size less the smallest
        # threshold any unvisited size can carry, a similar
        # set shares at least one prefix shingle and stands
        # in that shingle posting. The candidates the prefix
        # postings name stand judged exactly, set against
        # set, and no other unvisited set can stand similar
        # to the seed. The counting form this replaces read
        # the posting of every seed shingle at every seed,
        # which a pool shared in varying subsets priced at
        # the product of the set count and the unvisited
        # count, no pool shingle standing universal and the
        # base standing at zero while every set stood
        # counted in full. The frontier bound that read the
        # counting pass results now reads the exact shared
        # count with the seed at the place it stands used,
        # in possible_positions below.
        first_layer = []
        if remaining:
            lowest_threshold = band_lowest_threshold(seed_size)
            if lowest_threshold is not None:
                prefix_length = seed_size - lowest_threshold + 1
                if prefix_length < 1:
                    prefix_length = 1
                if prefix_length > seed_size:
                    prefix_length = seed_size
                prefix = ordered_set(seed)[:prefix_length]
                # The counted reading stands taken where
                # the wide reading itself stood taken in
                # full, and beside it wherever the exact form
                # judgement of the prefix form stands priced
                # past it: that price stands at the candidate
                # count the prefix postings can name, bounded
                # by the posting total and by the unvisited
                # count, times the seed size, and a price
                # past 50,000 stands counted instead, at any
                # seed size and at any prefix posting total.
                # The counted reading stands exact on every
                # family it stands taken on, as its own
                # statement states, naming the same layer, so
                # no guard on the seed size and no guard on
                # the posting total stands between a family
                # and the backstop on this pass.
                prefix_total = sum(unvisited_count[shingle]
                                   for shingle in prefix)
                take_counted = (remaining >= 256
                                and seed_size <= 2000
                                and prefix_total > 1024) \
                    or min(remaining, prefix_total) * seed_size \
                    > 50000
                if take_counted:
                    first_layer = counted_seed_layer()
                else:
                    candidates = set()
                    for shingle in prefix:
                        for other in postings[shingle]:
                            if not visited[other]:
                                candidates.add(other)
                    for other in sorted(candidates):
                        shared = len(sets[other] & seed_set)
                        if shared * 9 >= 4 * (
                                seed_size + len(sets[other])):
                            first_layer.append(other)
        frontier = []
        for other in first_layer:
            if not visited[other]:
                mark(other)
                component.append(other)
                frontier.append(other)
        # The work of one component stands organised in two
        # queues. The first queue is the frontier itself:
        # layer by layer, candidates standing in the light
        # postings of the frontier stand counted against
        # each frontier member on that member's own
        # threshold, and the ones the per member bounds
        # leave open stand judged exactly at once. The
        # first queue stands processed first and to
        # exhaustion. A candidate standing in no light
        # posting shares only heavy shingles with the
        # frontier; where the per member bounds exclude it
        # for every member of the layer it does not stand
        # judged, sorted, and rescanned at the next layer
        # in the old form. It passes to the second queue,
        # deferred in a form that can still complete: the
        # set itself, named once, judged once against the
        # whole component when the first queue stands
        # exhausted. A deferred set that later stands in a
        # light posting has a frontier partner in hand, a
        # solution path already standing, so it leaves the
        # second queue and stands worked in the first
        # queue ahead of the second queue's own turn. A
        # deferred set that joins from the second queue
        # becomes frontier, the first queue resumes ahead
        # of the deferred sets still waiting, and the
        # deferred sets already judged in that pass stand
        # judged again against the grown component, so no
        # join through a deferred set is ever lost.
        deferred = set()
        deferred_order = []
        # deferred_listed names the sets standing in
        # deferred_order. Promotion out of the second queue
        # discards a set from deferred alone, so a set that
        # is deferred, promoted without joining, and deferred
        # again stands named once in the order, as the two
        # queue statement above states the form: named once,
        # judged once in one pass.
        deferred_listed = set()
        deferred_judged = {}
        while True:
            while frontier and remaining:
                frontier_shingles = set()
                for node in frontier:
                    frontier_shingles.update(sets[node])
                frontier_by_shingle = {}
                for position, node in enumerate(frontier):
                    for shingle in sets[node]:
                        frontier_by_shingle.setdefault(
                            shingle, []).append(position)
                # The candidates of a layer stand counted
                # against each frontier member on that
                # member's own terms before any one of them
                # stands judged. A shingle whose posting
                # holds more unvisited sets than the heavy
                # bound is a heavy shingle: a candidate
                # shares at most every heavy shingle of a
                # member with that member, so its light
                # count plus the smaller of its heavy count
                # and the member's heavy count bounds its
                # shared count with that member, and its
                # shared count with the seed plus the part
                # of the member standing outside the seed
                # bounds it again. A member whose size
                # alone cannot reach the bound for the
                # candidate's size stands impossible for
                # that candidate whatever the counts say.
                # A candidate excluded on every member's
                # own threshold stands excluded in bulk for
                # this layer, where the old form priced
                # every candidate against the smallest
                # frontier member alone and a mixed size
                # frontier let a reject pool through at
                # every layer.
                heavy = {
                    shingle for shingle in frontier_shingles
                    if unvisited_count[shingle] > 96}
                member_sizes = [len(sets[node]) for node in frontier]
                member_heavy = [
                    len(sets[node] & heavy) if heavy else 0
                    for node in frontier]
                member_added = [
                    len(sets[node] - seed_set) for node in frontier]
                light_counts = {}
                for shingle in frontier_shingles:
                    if shingle in heavy:
                        continue
                    for other in postings[shingle]:
                        if not visited[other]:
                            light_counts[other] = \
                                light_counts.get(other, 0) + 1

                def possible_positions(other, light_shared,
                                       heavy_shared):
                    other_size = len(sets[other])
                    shared_seed = len(sets[other] & seed_set)
                    positions = []
                    for position in range(len(frontier)):
                        size = member_sizes[position]
                        if min(other_size, size) * 9 < \
                                4 * (other_size + size):
                            continue
                        threshold = -(-4 * (other_size + size) // 9)
                        if light_shared + min(
                                heavy_shared,
                                member_heavy[position]) < threshold:
                            continue
                        if shared_seed + member_added[position] < \
                                threshold:
                            continue
                        positions.append(position)
                    return positions

                candidates = {}
                for other, light_shared in light_counts.items():
                    if other in deferred:
                        deferred.discard(other)
                    heavy_shared = \
                        len(sets[other] & heavy) if heavy else 0
                    positions = possible_positions(
                        other, light_shared, heavy_shared)
                    if positions:
                        candidates[other] = positions
                if heavy:
                    # A set standing in no light posting
                    # shares at most the heavy part of a
                    # member with it, so the heavy part alone
                    # must reach the smallest threshold that
                    # member can carry, at the smallest
                    # candidate size that member can stand
                    # similar to, before any such set can
                    # join at this layer. Where no member
                    # passes that test the enumeration does
                    # not stand run at all.
                    def heavy_can_reach(position):
                        size = member_sizes[position]
                        smallest = -(-4 * size // 5)
                        threshold = -(-4 * (smallest + size) // 9)
                        return member_heavy[position] >= threshold

                    if any(heavy_can_reach(position)
                           for position in range(len(frontier))):
                        for size, members in list(by_size.items()):
                            for other in members:
                                if other in light_counts:
                                    continue
                                if other in deferred:
                                    continue
                                heavy_shared = len(sets[other] & heavy)
                                if not heavy_shared:
                                    continue
                                positions = possible_positions(
                                    other, 0, heavy_shared)
                                if positions:
                                    candidates[other] = positions
                                else:
                                    deferred.add(other)
                                    if other not in deferred_listed:
                                        deferred_listed.add(other)
                                        deferred_order.append(other)
                if not candidates:
                    break
                new_frontier = []
                for other, positions in candidates.items():
                    if visited[other]:
                        continue
                    other_size = len(sets[other])
                    allowance = max(
                        other_size - -(
                            -4 * (other_size + member_sizes[position])
                            // 9)
                        for position in positions)
                    if allowance < 0:
                        continue
                    picked = sorted(
                        sets[other],
                        key=lambda shingle: len(
                            frontier_by_shingle.get(shingle, ()))
                    )[:allowance + 1]
                    position_set = set(positions)
                    picked_positions = set()
                    for shingle in picked:
                        for position in frontier_by_shingle.get(
                                shingle, ()):
                            if position in position_set:
                                picked_positions.add(position)
                    joined = False
                    for position in picked_positions:
                        node = frontier[position]
                        shared = len(sets[other] & sets[node])
                        if shared * 9 >= 4 * (
                                other_size + len(sets[node])):
                            joined = True
                            break
                    if joined:
                        mark(other)
                        component.append(other)
                        new_frontier.append(other)
                frontier = new_frontier
            if not deferred:
                break
            # The second queue, worked only where the first
            # queue stands exhausted, apart from the
            # promotion the first queue itself grants above.
            # Each deferred set stands judged against the
            # whole component, by size class first: a class
            # whose members the set's shared count with the
            # whole component union cannot reach, or whose
            # size the set's size cannot stand similar to,
            # stands excluded whole, and only a class the
            # bounds leave open stands judged exactly,
            # member by member.
            snapshot = [other for other in deferred_order
                        if other in deferred]
            deferred = set()
            deferred_order = []
            deferred_listed = set()
            # A deferred set stands judged in this pass
            # against the part of the component that stands
            # new to it, and against no part it already
            # failed. No set changes as the component grows,
            # so a set that failed against the members of an
            # earlier pass cannot join through those members
            # in a later one, and deferred_judged records the
            # component length through which each waiting
            # set stands judged. The snapshot stands grouped
            # by that length, each group judged against the
            # members past its length alone, by size class
            # first in the form this pass has always stated.
            # The form this replaces rebuilt the component
            # union and read every waiting set against the
            # whole component at every pass, which a chain
            # joining one link per pass priced at the
            # product of the pass count and the deferred
            # count. The queue order stands untouched: this
            # pass stands worked only where the first queue
            # stands exhausted, a set that joins here stands
            # as frontier with the first queue resuming ahead
            # of the sets still waiting, and a waiting set
            # the first queue promotes stands worked there
            # ahead of this turn.
            component_at_pass = list(component)
            pass_length = len(component_at_pass)
            by_watermark = {}
            for other in snapshot:
                if visited[other]:
                    continue
                by_watermark.setdefault(
                    deferred_judged.get(other, 0), []).append(other)
            failures = []
            joined_list = []
            for watermark, group in by_watermark.items():
                check_members = component_at_pass[watermark:]
                if not check_members:
                    failures.extend(group)
                    continue
                if len(check_members) == 1:
                    node = check_members[0]
                    node_set = sets[node]
                    node_size = len(node_set)
                    for other in group:
                        other_size = len(sets[other])
                        shared = len(sets[other] & node_set)
                        if shared * 9 >= 4 * (other_size + node_size):
                            mark(other)
                            component.append(other)
                            joined_list.append(other)
                            deferred_judged.pop(other, None)
                        else:
                            failures.append(other)
                            deferred_judged[other] = pass_length
                    continue
                check_union = set()
                for node in check_members:
                    check_union.update(sets[node])
                check_by_size = {}
                for node in check_members:
                    check_by_size.setdefault(
                        len(sets[node]), []).append(node)
                for other in group:
                    other_size = len(sets[other])
                    union_shared = len(sets[other] & check_union)
                    joined = False
                    for size, members in check_by_size.items():
                        if min(other_size, size) * 9 < \
                                4 * (other_size + size):
                            continue
                        threshold = -(-4 * (other_size + size) // 9)
                        if union_shared < threshold:
                            continue
                        for node in members:
                            shared = len(sets[other] & sets[node])
                            if shared * 9 >= 4 * (other_size + size):
                                joined = True
                                break
                        if joined:
                            break
                    if joined:
                        mark(other)
                        component.append(other)
                        joined_list.append(other)
                        deferred_judged.pop(other, None)
                    else:
                        failures.append(other)
                        deferred_judged[other] = pass_length
            if not joined_list:
                break
            deferred_order = failures
            deferred_listed = set(failures)
            deferred = set(failures)
            frontier = joined_list
        components.append(component)
    return components
