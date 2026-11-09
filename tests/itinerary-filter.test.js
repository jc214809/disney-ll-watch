const test = require('node:test');
const assert = require('node:assert');
const { isSpecialShowtime, isVisible } = require('../itinerary-filter.js');

const times = n => Array.from({ length: n }, (_, i) => ({ key: `1${i}:00`, time: `${i}` }));

test('regular show with <=2 times is visible without the toggle', () => {
    assert.ok(isVisible({ meet: false, special: false, times: times(2) }, false, 2));
});

test('regular show with >2 times or a meet is hidden without the toggle', () => {
    assert.ok(!isVisible({ meet: false, special: false, times: times(3) }, false, 2));
    assert.ok(!isVisible({ meet: true, special: false, times: times(1) }, false, 2));
});

test('toggle on shows everything', () => {
    assert.ok(isVisible({ meet: true, special: false, times: times(5) }, true, 2));
});

test('special (party) items show even as a meet or with many times, toggle off', () => {
    assert.ok(isVisible({ meet: true, special: true, times: times(1) }, false, 2));
    assert.ok(isVisible({ meet: false, special: true, times: times(4) }, false, 2));
});

test('isSpecialShowtime matches only Special Ticketed Event, tolerating bad input', () => {
    assert.ok(isSpecialShowtime({ type: 'Special Ticketed Event' }));
    assert.ok(!isSpecialShowtime({ type: 'Performance Time' }));
    assert.ok(!isSpecialShowtime({}));
    assert.ok(!isSpecialShowtime(undefined));
});
