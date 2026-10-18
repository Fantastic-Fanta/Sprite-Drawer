//! CPython's iteration order for a small set of (r, g, b) tuples of small ints, so that
//! `max(set(cols), key=cols.count)` picks the same colour as Python does on a tie.
//! (Tuple hash: CPython's xxHash-based tuplehash; table: 8 slots, linear probes + perturbation,
//! grown to the next power of two above used * 4 once 3/5 full.)

const P1: u64 = 11400714785074694791;
const P2: u64 = 14029467366897019727;
const P5: u64 = 2870177450012600261;

fn tuple_hash(k: u32) -> u64 {
    let mut acc = P5;
    for v in [(k >> 16) & 255, (k >> 8) & 255, k & 255] {
        acc = acc.wrapping_add((v as u64).wrapping_mul(P2));
        acc = acc.rotate_left(31);
        acc = acc.wrapping_mul(P1);
    }
    acc = acc.wrapping_add(3 ^ (P5 ^ 3527539));
    if acc == u64::MAX { 1546275796 } else { acc }
}

fn insert(table: &mut [Option<(u64, u32)>], h: u64, key: u32) -> bool {
    let mask = table.len() - 1;
    let mut i = (h as usize) & mask;
    let mut perturb = h;
    loop {
        let mut probes = if i + 9 <= mask { 9 } else { 0 };
        let mut j = i;
        loop {
            match table[j] {
                None => { table[j] = Some((h, key)); return true; }
                Some((hh, kk)) if hh == h && kk == key => return false,
                _ => {}
            }
            if probes == 0 { break; }
            probes -= 1;
            j += 1;
        }
        perturb >>= 5;
        i = (i.wrapping_mul(5).wrapping_add(1).wrapping_add(perturb as usize)) & mask;
    }
}

/// `max(set(items), key=items.count)` for colour keys (r << 16 | g << 8 | b); items non-empty
pub fn most_common(items: &[u32]) -> u32 {
    let mut table: Vec<Option<(u64, u32)>> = vec![None; 8];
    let mut used = 0usize;
    for &k in items {
        if insert(&mut table, tuple_hash(k), k) {
            used += 1;
            if used * 5 >= (table.len() - 1) * 3 {
                let mut size = 8;
                while size <= used * 4 { size <<= 1; }
                let old: Vec<(u64, u32)> = table.iter().flatten().copied().collect();
                table = vec![None; size];
                for (hh, kk) in old { insert(&mut table, hh, kk); }
            }
        }
    }
    let mut best = 0u32;
    let mut best_n = 0usize;
    for (_, k) in table.iter().flatten() {
        let n = items.iter().filter(|&&v| v == *k).count();
        if n > best_n { best = *k; best_n = n; }
    }
    best
}
