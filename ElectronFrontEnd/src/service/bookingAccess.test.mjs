import assert from 'node:assert/strict';

import { resolveBookingAccess } from './bookingAccess.mjs';

assert.deepEqual(resolveBookingAccess({ partner_bookings: [{}] }), {
    bookingCount: 1,
    hasSessionOne: true,
    hasAdvancedBooking: false,
    hasSessionThree: false,
});

assert.equal(resolveBookingAccess([{}]).hasAdvancedBooking, false);

assert.deepEqual(resolveBookingAccess({ bookings: [{}, {}] }), {
    bookingCount: 2,
    hasSessionOne: true,
    hasAdvancedBooking: true,
    hasSessionThree: false,
});

assert.deepEqual(resolveBookingAccess({ booking_count: 3 }), {
    bookingCount: 3,
    hasSessionOne: true,
    hasAdvancedBooking: true,
    hasSessionThree: true,
});

assert.equal(resolveBookingAccess({ has_booking: true }).bookingCount, 1);
assert.equal(resolveBookingAccess({ data: { booking_count: 0 } }).hasSessionOne, false);
